import pytest

from upload.file_checksum import FileChecksums
from upload.upload_plan_request import (
    DEFAULT_PART_SIZE,
    MAX_FILES_PER_REQUEST,
    MAX_OBJECT_SIZE,
    MAX_PART_SIZE,
    MAX_URLS_PER_REQUEST,
    MULTIPART_THRESHOLD,
    UploadPlanFileRequest,
    part_size_for,
    split_requests,
)

MiB = 1024 * 1024


class TestPartSize:
    def test_below_threshold_is_single(self):
        assert part_size_for(MULTIPART_THRESHOLD - 1) is None

    def test_threshold_itself_is_multipart(self):
        # 서버와 같은 "100MiB 미만/이상" 기준. 정확히 100MiB는 멀티파트다.
        assert part_size_for(MULTIPART_THRESHOLD) == DEFAULT_PART_SIZE

    def test_largest_object_fits_one_request(self):
        # 가장 큰 파일도 조각 크기가 S3 상한 안이고 조각 수가 요청 하나의 URL 상한 안이다.
        part_size = part_size_for(MAX_OBJECT_SIZE)

        assert part_size is not None
        assert part_size <= MAX_PART_SIZE
        assert -(-MAX_OBJECT_SIZE // part_size) <= MAX_URLS_PER_REQUEST

    def test_over_s3_object_limit_is_rejected(self):
        with pytest.raises(ValueError):
            part_size_for(MAX_OBJECT_SIZE + 1)


def _single(file_id: str = "df-1", size: int = 5 * MiB) -> UploadPlanFileRequest:
    return UploadPlanFileRequest(
        detail_file_public_id=file_id,
        size=size,
        checksums=FileChecksums(sha256="sha"),
    )


def _multipart(file_id: str = "df-2", parts: int = 2) -> UploadPlanFileRequest:
    return UploadPlanFileRequest(
        detail_file_public_id=file_id,
        size=parts * DEFAULT_PART_SIZE,
        checksums=FileChecksums(
            sha256="sha",
            part_size=DEFAULT_PART_SIZE,
            part_crc64=tuple(f"crc{n}" for n in range(1, parts + 1)),
            crc64="full",
        ),
    )


class TestRequestBody:
    def test_single_sends_no_multipart_keys(self):
        # 방식에 없는 키는 null로도 보내면 서버가 거절한다.
        assert _single().to_api_dict() == {
            "detailFilePublicId": "df-1",
            "size": 5 * MiB,
            "sha256": "sha",
        }

    def test_multipart_numbers_part_checksums_from_one(self):
        body = _multipart(parts=2).to_api_dict()

        assert body["checksumAlgorithm"] == "CRC64NVME"
        assert body["partSize"] == DEFAULT_PART_SIZE
        assert body["partChecksums"] == [
            {"partNumber": 1, "value": "crc1"},
            {"partNumber": 2, "value": "crc2"},
        ]
        assert body["checksum"] == "full"
        assert "mode" not in body


class TestSplitRequests:
    def test_splits_by_file_count(self):
        files = [_single(f"df-{n}") for n in range(MAX_FILES_PER_REQUEST + 1)]

        groups = split_requests(files)

        assert [len(g) for g in groups] == [MAX_FILES_PER_REQUEST, 1]

    def test_fills_up_to_url_limit(self):
        files = [
            _multipart("df-a", parts=MAX_URLS_PER_REQUEST - 1),
            _single("df-b"),
            _single("df-c"),
        ]

        groups = split_requests(files)

        assert [len(g) for g in groups] == [2, 1]
        assert all(sum(f.url_count for f in g) <= MAX_URLS_PER_REQUEST for g in groups)
