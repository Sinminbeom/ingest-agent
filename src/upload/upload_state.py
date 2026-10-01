from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import StrEnum
from typing import Any

from upload.upload_errors import ChecksumMismatchError
from upload.upload_plan import UploadFilePlan

from utils.util import utc_now_iso


class FileUploadStatus(StrEnum):
    PENDING = "PENDING"
    UPLOADED = "UPLOADED"
    FAILED = "FAILED"


@dataclass
class FileUploadState:
    """파일 하나의 업로드 플랜 + 파트 단위 진행 상태.

    파트는 원자적이므로(중간에 끊긴 파트는 S3에 저장되지 않음) completed_etags에
    기록된 파트는 "완료", 없는 파트는 "미시작"으로 판정할 수 있다 — 애매한 중간
    상태가 없어 재개 판정이 단순하다.

    재개할 때 기대 체크섬(sha256·플랜 헤더)은 다시 계산하지 않는다.
    """

    plan: UploadFilePlan
    src_path: str
    size_bytes: int
    sha256: str
    file_kind: str
    project_public_id: str | None
    sample_public_id: str | None
    dst_url: str
    # partNumber -> ETag(따옴표 포함 원문). CompleteMultipartUpload XML에 그대로 쓴다.
    completed_etags: dict[int, str] = field(default_factory=dict)
    status: FileUploadStatus = FileUploadStatus.PENDING
    fail_code: str | None = None
    fail_msg: str | None = None
    fail_at: str | None = None
    fail_retryable: bool = False
    detected_at: str | None = None
    uploaded_at: str | None = None

    @property
    def detail_file_public_id(self) -> str:
        return self.plan.detail_file_public_id

    def pending_part_numbers(self) -> list[int]:
        return [
            part.part_number
            for part in self.plan.parts
            if part.part_number not in self.completed_etags
        ]

    def record_part(self, part_number: int, etag: str) -> None:
        self.completed_etags[part_number] = etag

    def merge_listed_parts(self, listed_etags: dict[int, str]) -> None:
        """ListParts 결과를 로컬 기록에 병합한다.

        파트 PUT은 성공했으나 응답이 유실돼 ETag를 못 받은 파트를 재전송 없이
        회수하는 경로. 로컬 기록이 이미 있는 파트는 로컬을 유지한다.
        """
        for part_number, etag in listed_etags.items():
            self.completed_etags.setdefault(part_number, etag)

    def mark_detected(self) -> None:
        if self.detected_at is None:
            self.detected_at = utc_now_iso()

    def mark_uploaded(self) -> None:
        self.status = FileUploadStatus.UPLOADED
        self.uploaded_at = utc_now_iso()

    def mark_failed(self, code: str, msg: str, retryable: bool) -> None:
        self.status = FileUploadStatus.FAILED
        self.fail_code = code
        self.fail_msg = msg
        self.fail_at = utc_now_iso()
        self.fail_retryable = retryable

    def reset_for_retry(self) -> None:
        """실패 상태를 풀고 재시도 대상으로 되돌린다. 완료된 파트 기록은 유지한다."""
        self.status = FileUploadStatus.PENDING
        self.fail_code = None
        self.fail_msg = None
        self.fail_at = None
        self.fail_retryable = False

    @property
    def is_terminal(self) -> bool:
        return self.status != FileUploadStatus.PENDING

    def to_dict(self) -> dict[str, Any]:
        return {
            "plan": self.plan.to_dict(),
            "srcPath": self.src_path,
            "sizeBytes": self.size_bytes,
            "sha256": self.sha256,
            "fileKind": self.file_kind,
            "projectPublicId": self.project_public_id,
            "samplePublicId": self.sample_public_id,
            "dstUrl": self.dst_url,
            "completedParts": [
                {"partNumber": part_number, "etag": etag}
                for part_number, etag in sorted(self.completed_etags.items())
            ],
            "status": str(self.status),
            "failCode": self.fail_code,
            "failMsg": self.fail_msg,
            "failAt": self.fail_at,
            "failRetryable": self.fail_retryable,
            "detectedAt": self.detected_at,
            "uploadedAt": self.uploaded_at,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> FileUploadState:
        return cls(
            plan=UploadFilePlan.from_dict(data["plan"]),
            src_path=str(data["srcPath"]),
            size_bytes=int(data["sizeBytes"]),
            sha256=str(data["sha256"]),
            file_kind=str(data["fileKind"]),
            project_public_id=data.get("projectPublicId"),
            sample_public_id=data.get("samplePublicId"),
            dst_url=str(data["dstUrl"]),
            completed_etags={
                int(p["partNumber"]): str(p["etag"])
                for p in data.get("completedParts") or []
            },
            status=FileUploadStatus(data["status"]),
            fail_code=data.get("failCode"),
            fail_msg=data.get("failMsg"),
            fail_at=data.get("failAt"),
            fail_retryable=bool(data.get("failRetryable", False)),
            detected_at=data.get("detectedAt"),
            uploaded_at=data.get("uploadedAt"),
        )


@dataclass
class BatchUploadState:
    """배치 하나의 업로드 진행 스냅샷 — 절전·재시작·네트워크 끊김 재개의 단일 근거.

    플랜(프리사인드 URL 전체)과 status_token까지 담아, 재개 시 api-server 재호출
    없이 업로드 완주 + meta.json 업로드 + 상태 보고까지 마칠 수 있다.
    """

    tenant_public_id: str
    batch_public_id: str
    seq_id: str
    expires_at: str
    meta_json_url: str
    status_token: str
    files: list[FileUploadState]
    requested_at: str | None = None
    meta_json: dict[str, Any] | None = None

    def is_expired(self, now: datetime | None = None) -> bool:
        now = now or datetime.now(timezone.utc)
        expires = datetime.fromisoformat(self.expires_at.replace("Z", "+00:00"))
        return now >= expires

    def mark_requested(self) -> None:
        if self.requested_at is None:
            self.requested_at = utc_now_iso()

    def pending_files(self) -> list[FileUploadState]:
        return [f for f in self.files if f.status == FileUploadStatus.PENDING]

    def has_checksum_mismatch(self) -> bool:
        return any(
            f.status == FileUploadStatus.FAILED
            and f.fail_code == ChecksumMismatchError.CODE
            for f in self.files
        )

    def reset_failed_for_retry(self, include_permanent: bool) -> None:
        for f in self.files:
            if f.status != FileUploadStatus.FAILED:
                continue
            if f.fail_retryable or include_permanent:
                f.reset_for_retry()
                # 파일을 다시 올리면 결과가 바뀌므로 확정했던 meta.json도 다시 만든다.
                self.meta_json = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "tenantPublicId": self.tenant_public_id,
            "batchPublicId": self.batch_public_id,
            "seqId": self.seq_id,
            "expiresAt": self.expires_at,
            "metaJsonUrl": self.meta_json_url,
            "statusToken": self.status_token,
            "requestedAt": self.requested_at,
            "metaJson": self.meta_json,
            "files": [f.to_dict() for f in self.files],
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> BatchUploadState:
        return cls(
            tenant_public_id=str(data["tenantPublicId"]),
            batch_public_id=str(data["batchPublicId"]),
            seq_id=str(data["seqId"]),
            expires_at=str(data["expiresAt"]),
            meta_json_url=str(data["metaJsonUrl"]),
            status_token=str(data["statusToken"]),
            files=[FileUploadState.from_dict(f) for f in data["files"]],
            requested_at=data.get("requestedAt"),
            meta_json=data.get("metaJson"),
        )
