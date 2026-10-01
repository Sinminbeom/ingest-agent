from dataclasses import asdict
from threading import Lock
from typing import Any

from config.project_config import ProjectConfig
from job_container.job_container import JobContainer
from meta.batch import (
    Acquisition,
    Batch,
    BatchContent,
    BatchIdentifiers,
    Diagnostics,
    Source,
    Timestamps,
)
from meta.sample import (
    Checksum,
    Content,
    File,
    FileDiagnostics,
    FileTimestamps,
    Sample,
    SampleIdentifiers,
)
from upload.upload_errors import UploadError
from upload.upload_state import FileUploadState, FileUploadStatus
from utils.util import utc_now_iso


class BatchContainer:
    STATUS_SUCCESS = "SUCCESS"
    STATUS_FAILED = "FAILED"
    CHECKSUM_ALGO = "SHA256"
    KIND_SAMPLE = "SAMPLE"
    # meta.json에서 NON_SAMPLE 파일은 sample 하나에 모은다.
    NON_SAMPLE_KEY = ""

    def __init__(self, batch_public_id: str, tenant_public_id: str) -> None:
        self.name: str = batch_public_id
        self.job: JobContainer = JobContainer()
        self._job_lock = Lock()
        self.samples: dict[str, Sample] = {}
        self.files: dict[str, File] = {}

        config = ProjectConfig.instance()
        self.schema: str = config.meta_schema_url
        self.batch = Batch(
            identifiers=BatchIdentifiers(
                tenant_uuid=tenant_public_id, batch_uuid=batch_public_id
            ),
            content=BatchContent(
                source=Source(
                    type="agent",
                    name=config.project_name,
                    version=config.project_version,
                ),
                acquisition=Acquisition(
                    software={
                        "name": config.software_name,
                        "version": config.software_version,
                    },
                    mode={"code": config.mode_code, "uri": config.mode_url},
                ),
            ),
            timestamps=Timestamps(),
            status=self.STATUS_SUCCESS,
            diagnostics=Diagnostics(warnings=[], errors=[]),
            extensions={},
        )

    @property
    def batch_public_id(self) -> str:
        return self.name

    def add_file(self, file_state: FileUploadState) -> None:
        # 같은 프로세스에서 다시 시도하면 이미 등록돼 있다.
        file_id = file_state.detail_file_public_id
        if file_id in self.files:
            return
        file = File(
            uri=file_state.dst_url,
            size_bytes=file_state.size_bytes,
            checksum=Checksum(algo=self.CHECKSUM_ALGO, value=file_state.sha256),
            timestamps=FileTimestamps(),
            status="",
            diagnostics=FileDiagnostics(),
        )
        self._sample_of(file_state).content.files.append(file)
        self.files[file_id] = file

    def _sample_of(self, file_state: FileUploadState) -> Sample:
        key = (
            file_state.sample_public_id or ""
            if file_state.file_kind == self.KIND_SAMPLE
            else self.NON_SAMPLE_KEY
        )
        sample = self.samples.get(key)
        if sample is None:
            sample = Sample(
                identifiers=SampleIdentifiers(
                    project_uuid=file_state.project_public_id or "",
                    sample_uuid=file_state.sample_public_id or "",
                    file_kind=file_state.file_kind,
                ),
                content=Content(files=[]),
                extensions={},
            )
            self.samples[key] = sample
        return sample

    def restore_file(self, file_state: FileUploadState) -> None:
        file = self.file(file_state.detail_file_public_id)
        file.timestamps.detected_at = file_state.detected_at
        if file_state.status == FileUploadStatus.UPLOADED:
            self._success(file, file_state.uploaded_at)
        elif file_state.status == FileUploadStatus.FAILED:
            self._fail(
                file,
                file_state.fail_code or UploadError.CODE,
                file_state.fail_msg or "",
                file_state.fail_at,
            )

    def file(self, detail_file_public_id: str) -> File:
        found = self.files.get(detail_file_public_id)
        if found is None:
            raise ValueError(
                f"File not found in batch: detail_file_public_id={detail_file_public_id}"
            )
        return found

    def has_failed_file(self) -> bool:
        return any(f.status == File.E_FILE_STATUS.FAIL for f in self.files.values())

    def mark_file_detected(self, detail_file_public_id: str) -> None:
        self.file(detail_file_public_id).timestamps.mark_detected()

    def mark_file_uploaded(self, detail_file_public_id: str, uploaded_at: str) -> None:
        self._success(self.file(detail_file_public_id), uploaded_at)

    def mark_file_failed(
        self, detail_file_public_id: str, code: str, msg: str, at: str | None
    ) -> None:
        self._fail(self.file(detail_file_public_id), code, msg, at)

    @staticmethod
    def _success(file: File, uploaded_at: str | None) -> None:
        at = uploaded_at or utc_now_iso()
        file.timestamps.uploaded_at = at
        file.timestamps.verified_at = at
        file.diagnostics.error = None
        file.success()

    @staticmethod
    def _fail(file: File, code: str, msg: str, at: str | None) -> None:
        file.fail(code, msg)
        if at is not None and file.diagnostics.error is not None:
            file.diagnostics.error.at = at

    def add_marker(self, detail_file_public_id: str) -> None:
        self.job.add_marker(detail_file_public_id)

    def mark_complete(self, detail_file_public_id: str) -> None:
        self.job.mark_complete(detail_file_public_id)

    def complete_file(self, detail_file_public_id: str) -> bool:
        # 업로드 스레드 여러 개가 동시에 끝나도 마지막 파일을 정확히 한 번만 알린다.
        with self._job_lock:
            self.job.mark_complete(detail_file_public_id)
            return self.job.is_all_completed()

    def restore_requested_at(self, requested_at: str | None) -> None:
        """재개 시 영속화된 최초 요청 시각을 복원한다."""
        self.batch.timestamps.requested_at = requested_at

    def mark_requested(self) -> None:
        # 재개 시 복원된 최초 요청 시각을 덮어쓰지 않는다.
        self.batch.timestamps.mark_requested()

    def mark_ingested(self) -> None:
        self.batch.timestamps.ingested_at = utc_now_iso()

    def to_schema_dict(self) -> dict[str, Any]:
        self.batch.status = (
            self.STATUS_FAILED if self.has_failed_file() else self.STATUS_SUCCESS
        )
        return {
            "$schema": self.schema,
            "batch": asdict(self.batch),
            "samples": [asdict(s) for s in self.samples.values()],
        }
