import base64
import hashlib

import pytest
from awscrt import checksums

from upload.file_checksum import LocalFileChangedError, compute_checksums

# 읽기 단위(chunk)보다 조각이 커서 조각 경계와 읽기 경계가 어긋나는 경우를 만든다.
PART_SIZE = 10
CHUNK_SIZE = 4
BODY = bytes(range(256)) * 3 + b"tail"  # 772바이트 → 조각 78개, 마지막 2바이트


def _b64_crc(data: bytes) -> str:
    return base64.b64encode(checksums.crc64nvme(data).to_bytes(8, "big")).decode()


@pytest.fixture
def src_file(tmp_path):
    path = tmp_path / "body.raw"
    path.write_bytes(BODY)
    return str(path)


def test_single_computes_sha256_only(src_file):
    result = compute_checksums(src_file, len(BODY), None, chunk_size=CHUNK_SIZE)

    assert result.sha256 == base64.b64encode(hashlib.sha256(BODY).digest()).decode()
    assert result.part_size is None
    assert result.part_crc64 == ()
    assert result.crc64 is None


def test_multipart_part_crcs_follow_part_boundaries(src_file):
    result = compute_checksums(src_file, len(BODY), PART_SIZE, chunk_size=CHUNK_SIZE)

    expected_parts = tuple(
        _b64_crc(BODY[offset : offset + PART_SIZE])
        for offset in range(0, len(BODY), PART_SIZE)
    )
    assert result.part_crc64 == expected_parts
    assert result.crc64 == _b64_crc(BODY)
    assert result.sha256 == base64.b64encode(hashlib.sha256(BODY).digest()).decode()


def test_multipart_exact_multiple_has_no_empty_last_part(tmp_path):
    body = b"x" * (PART_SIZE * 3)
    path = tmp_path / "exact.raw"
    path.write_bytes(body)

    result = compute_checksums(str(path), len(body), PART_SIZE, chunk_size=CHUNK_SIZE)

    assert len(result.part_crc64) == 3


def test_size_mismatch_is_rejected(src_file):
    # 크기를 잰 뒤 파일이 바뀌면 계산한 체크섬을 서버에 보내지 않는다.
    with pytest.raises(LocalFileChangedError):
        compute_checksums(src_file, len(BODY) + 1, PART_SIZE)
