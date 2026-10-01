from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from upload.file_checksum import FileChecksums

# api-server와 같은 값이어야 한다. 서버가 크기로 방식을 정하고 범위 밖 요청을 거절한다.
MULTIPART_THRESHOLD = 100 * 1024 * 1024  # 미만은 단일 PUT, 이상은 멀티파트
DEFAULT_PART_SIZE = 100 * 1024 * 1024
MAX_PART_SIZE = 5 * 1024**3
MAX_OBJECT_SIZE = 5 * 1024**4
# 계획 응답은 URL마다 약 1KB라 API Gateway 본문 한도(10MB)와 응답 대기(30초) 안에 들도록
# 요청 하나의 URL·파일 수를 묶는다.
MAX_URLS_PER_REQUEST = 2_000
MAX_FILES_PER_REQUEST = 100

CHECKSUM_ALGORITHM = "CRC64NVME"


def part_size_for(size: int) -> int | None:
    # 파일 하나의 조각 수가 요청 하나의 URL 상한을 넘지 않도록 조각을 키운다.
    if size > MAX_OBJECT_SIZE:
        raise ValueError(f"File exceeds S3 max object size ({MAX_OBJECT_SIZE}): {size}")
    if size < MULTIPART_THRESHOLD:
        return None
    part_size = max(DEFAULT_PART_SIZE, -(-size // MAX_URLS_PER_REQUEST))
    return min(part_size, MAX_PART_SIZE)


@dataclass(frozen=True)
class UploadPlanFileRequest:
    # 방식에 없는 키는 null로도 보내면 서버가 거절한다.
    detail_file_public_id: str
    size: int
    checksums: FileChecksums

    @property
    def url_count(self) -> int:
        return len(self.checksums.part_crc64) or 1

    def to_api_dict(self) -> dict[str, Any]:
        body: dict[str, Any] = {
            "detailFilePublicId": self.detail_file_public_id,
            "size": self.size,
            "sha256": self.checksums.sha256,
        }
        if self.checksums.part_size is None:
            return body
        body.update(
            {
                "checksumAlgorithm": CHECKSUM_ALGORITHM,
                "partSize": self.checksums.part_size,
                "partChecksums": [
                    {"partNumber": n, "value": value}
                    for n, value in enumerate(self.checksums.part_crc64, start=1)
                ],
                "checksum": self.checksums.crc64,
            }
        )
        return body


def split_requests(
    files: list[UploadPlanFileRequest],
) -> list[list[UploadPlanFileRequest]]:
    groups: list[list[UploadPlanFileRequest]] = []
    current: list[UploadPlanFileRequest] = []
    urls = 0
    for file in files:
        if current and (
            len(current) == MAX_FILES_PER_REQUEST
            or urls + file.url_count > MAX_URLS_PER_REQUEST
        ):
            groups.append(current)
            current, urls = [], 0
        current.append(file)
        urls += file.url_count
    if current:
        groups.append(current)
    return groups
