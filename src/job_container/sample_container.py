from dataclasses import asdict
from typing import Any, Dict, List, Optional, Iterable

from job_container.base_node import BaseNode
from job_container.job_container import JobContainer
from meta.sample import Sample, SampleIdentifiers, Content, File, Checksum, FileTimestamps, FileDiagnostics


class SampleContainer(BaseNode):
    """sample_uuid 단위 노드.
    - 내부 JobContainer 기능은 그대로 유지
    - datalake-catalog schema용 Sample dataclass를 보유
    """

    def __init__(self, experiment_public_id: str, sample_public_id: str) -> None:
        self.job: JobContainer = JobContainer()

        self.sample = Sample(
            identifiers=SampleIdentifiers(experiment_public_id, sample_public_id),
            content=Content(files=[]),
            extensions={},
        )

    @property
    def experiment_public_id(self) -> str:
        return self.sample.identifiers.experiment_uuid

    @property
    def sample_public_id(self) -> str:
        return self.sample.identifiers.sample_uuid

    def add_file(self, url: str, size_bytes: int, checksum_algo: str, checksum_value: str) -> None:
        file = File(
            uri=url,
            size_bytes=size_bytes,
            checksum=Checksum(algo=checksum_algo, value=checksum_value),
            timestamps=FileTimestamps(),
            status="",
            diagnostics=FileDiagnostics()
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

    def to_schema_sample_dict(self) -> Dict[str, Any]:
        d = asdict(self.sample)
        ext = d.get("extensions") or {}
        # ext["job"] = self.job.to_dict()
        d["extensions"] = ext
        return d

    def to_dict(self) -> dict:
        # 기존 호출부 호환 + schema도 같이 노출
        return {"sample_public_id": self.sample_public_id, "job": self.job.to_dict(), "schema": self.to_schema_sample_dict()}
