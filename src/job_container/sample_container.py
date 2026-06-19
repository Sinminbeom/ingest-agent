from dataclasses import asdict
from typing import Any, Dict, Iterable

from job_container.base_node import BaseNode
from job_container.job_container import JobContainer
from meta.sample import (
    Sample,
    SampleIdentifiers,
    Content,
    File,
    Checksum,
    FileTimestamps,
    FileDiagnostics,
)


class SampleContainer(BaseNode):
    """project_sample(또는 NON_SAMPLE) 단위 노드.
    - 내부 JobContainer 기능은 그대로 유지
    - datalake-catalog schema용 Sample dataclass를 보유
    """

    KIND_SAMPLE = "SAMPLE"
    KIND_NON_SAMPLE = "NON_SAMPLE"

    def __init__(
        self, project_public_id: str, sample_public_id: str, file_kind: str
    ) -> None:
        self.job: JobContainer = JobContainer()

        self.sample = Sample(
            identifiers=SampleIdentifiers(
                project_public_id, sample_public_id, file_kind
            ),
            content=Content(files=[]),
            extensions={},
        )

    @property
    def project_public_id(self) -> str:
        return self.sample.identifiers.project_uuid

    @property
    def sample_public_id(self) -> str:
        return self.sample.identifiers.sample_uuid

    @property
    def file_kind(self) -> str:
        return self.sample.identifiers.file_kind

    def add_file(
        self, url: str, size_bytes: int, checksum_algo: str, checksum_value: str
    ) -> None:
        file = File(
            uri=url,
            size_bytes=size_bytes,
            checksum=Checksum(algo=checksum_algo, value=checksum_value),
            timestamps=FileTimestamps(),
            status="",
            diagnostics=FileDiagnostics(),
        )
        self.sample.content.files.append(file)

    # -------- Job 편의 메서드 (기존 유지) --------
    def add_markers(self, paths: Iterable[str]) -> None:
        self.job.add_markers(paths)

    def add_marker(self, path: str) -> None:
        self.job.add_marker(path)

    def mark_complete(self, marker: str) -> None:
        self.job.mark_complete(marker)

    def is_marker_done(self, marker: str) -> bool:
        return self.job.is_marker_done(marker)

    # -------- BaseNode 구현 --------
    def is_all_completed(self) -> bool:
        return self.job.is_all_completed()

    def clear_all(self) -> None:
        self.job.clear_all()

    def mark_file_detected(self, url: str) -> None:
        """
        업로드 시작(또는 발견) 시각: detected_at 기록
        """
        for f in self.sample.content.files:
            if f.uri == url:
                f.timestamps.mark_detected()
                return
        raise ValueError(f"File not found in sample: uri={url}")

    def mark_file_uploaded(self, url: str) -> None:
        """
        업로드 종료 시각: uploaded_at을 기록
        """
        for f in self.sample.content.files:
            if f.uri == url:
                f.timestamps.mark_uploaded()
                f.timestamps.mark_verified()
                f.success()
                return

        raise ValueError(f"File not found in sample: uri={url}")

    def mark_file_failed(self, url: str, code: str, msg: str) -> None:
        """
        파일 업로드 에러 mark
        """
        for f in self.sample.content.files:
            if f.uri == url:
                f.fail(code, msg)
                return

        raise ValueError(f"File not found in sample: uri={url}")

    def has_failed_file(self) -> bool:
        return any(
            f.status == File.E_FILE_STATUS.FAIL for f in self.sample.content.files
        )

    def to_schema_sample_dict(self) -> Dict[str, Any]:
        d = asdict(self.sample)
        ext = d.get("extensions") or {}
        d["extensions"] = ext
        return d

    def to_dict(self) -> dict:
        return {
            "sample_public_id": self.sample_public_id,
            "job": self.job.to_dict(),
            "schema": self.to_schema_sample_dict(),
        }
