from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import StrEnum
from typing import Any


class UploadMode(StrEnum):
    SINGLE = "SINGLE"
    MULTIPART = "MULTIPART"


@dataclass(frozen=True)
class UploadPartPlan:
    # 조각 체크섬이 서명에 들어 있어 headers를 그대로 싣지 않으면 S3가 거절한다.
    part_number: int
    url: str
    headers: dict[str, str] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "partNumber": self.part_number,
            "url": self.url,
            "headers": self.headers,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> UploadPartPlan:
        return cls(
            part_number=int(data["partNumber"]),
            url=str(data["url"]),
            headers=dict(data.get("headers") or {}),
        )


@dataclass(frozen=True)
class UploadFilePlan:
    # headers·parts[].headers·complete_headers의 체크섬은 재개할 때도 그대로 기대값으로 쓴다.
    detail_file_public_id: str
    key: str
    mode: UploadMode
    checksum_algorithm: str | None = None
    url: str | None = None
    headers: dict[str, str] = field(default_factory=dict)
    upload_id: str | None = None
    part_size: int | None = None
    parts: list[UploadPartPlan] = field(default_factory=list)
    complete_url: str | None = None
    complete_headers: dict[str, str] = field(default_factory=dict)
    abort_url: str | None = None
    list_parts_url: str | None = None

    @property
    def total_parts(self) -> int:
        return len(self.parts)

    def part(self, part_number: int) -> UploadPartPlan:
        for part in self.parts:
            if part.part_number == part_number:
                return part
        raise ValueError(f"Part not found in plan: part_number={part_number}")

    def to_dict(self) -> dict[str, Any]:
        return {
            "detailFilePublicId": self.detail_file_public_id,
            "key": self.key,
            "mode": str(self.mode),
            "checksumAlgorithm": self.checksum_algorithm,
            "url": self.url,
            "headers": self.headers,
            "uploadId": self.upload_id,
            "partSize": self.part_size,
            "parts": [part.to_dict() for part in self.parts],
            "completeUrl": self.complete_url,
            "completeHeaders": self.complete_headers,
            "abortUrl": self.abort_url,
            "listPartsUrl": self.list_parts_url,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> UploadFilePlan:
        # 서버는 방식에 없는 필드도 null·빈 값으로 내려준다.
        return cls(
            detail_file_public_id=str(data["detailFilePublicId"]),
            key=str(data["key"]),
            mode=UploadMode(data["mode"]),
            checksum_algorithm=data.get("checksumAlgorithm"),
            url=data.get("url"),
            headers=dict(data.get("headers") or {}),
            upload_id=data.get("uploadId"),
            part_size=data.get("partSize"),
            parts=[UploadPartPlan.from_dict(p) for p in data.get("parts") or []],
            complete_url=data.get("completeUrl"),
            complete_headers=dict(data.get("completeHeaders") or {}),
            abort_url=data.get("abortUrl"),
            list_parts_url=data.get("listPartsUrl"),
        )


@dataclass(frozen=True)
class UploadPlan:
    """api-server upload-plan 응답 (camelCase envelope 언래핑 후).

    meta_json_url·status_token은 업로드가 사용자 토큰
    수명(1시간)을 넘겨도 meta.json 업로드와 완료 상태 보고를 완주하기 위해
    플랜 발급 시점에 함께 받는다.
    """

    expires_at: str
    meta_json_url: str
    status_token: str
    files: list[UploadFilePlan]

    def is_expired(self, now: datetime | None = None) -> bool:
        now = now or datetime.now(timezone.utc)
        return now >= self._expires_datetime()

    def _expires_datetime(self) -> datetime:
        return datetime.fromisoformat(self.expires_at.replace("Z", "+00:00"))

    @classmethod
    def from_api_dict(cls, data: dict[str, Any]) -> UploadPlan:
        return cls(
            expires_at=str(data["expiresAt"]),
            meta_json_url=str(data["metaJsonUrl"]),
            status_token=str(data["statusToken"]),
            files=[UploadFilePlan.from_dict(f) for f in data["files"]],
        )

    @classmethod
    def merge(cls, plans: list[UploadPlan]) -> UploadPlan:
        # 가장 먼저 만료되는 계획에 맞춰야 모든 URL이 살아 있을 때만 전송한다.
        if not plans:
            raise ValueError("No upload plan to merge")
        earliest = min(plans, key=lambda p: p._expires_datetime())
        return cls(
            expires_at=earliest.expires_at,
            meta_json_url=earliest.meta_json_url,
            status_token=earliest.status_token,
            files=[f for p in plans for f in p.files],
        )
