from __future__ import annotations

import base64
import hashlib
from dataclasses import dataclass

from awscrt import checksums


class LocalFileChangedError(RuntimeError):
    pass


@dataclass(frozen=True)
class FileChecksums:
    # 값은 모두 Base64. part_size·part_crc64·crc64는 멀티파트일 때만 채운다.
    sha256: str
    part_size: int | None = None
    part_crc64: tuple[str, ...] = ()
    crc64: str | None = None


def compute_checksums(
    path: str, size: int, part_size: int | None, chunk_size: int = 1024 * 1024
) -> FileChecksums:
    # 전체 CRC는 조각 CRC를 합치지 않고 같은 읽기에서 이어서 계산한다.
    sha256 = hashlib.sha256()
    part_crcs: list[str] = []
    full_crc = 0
    part_crc = 0
    in_part = 0
    read_total = 0

    with open(path, "rb") as f:
        while True:
            want = chunk_size
            if part_size is not None:
                want = min(want, part_size - in_part)
            chunk = f.read(want)
            if not chunk:
                break
            read_total += len(chunk)
            sha256.update(chunk)
            if part_size is None:
                continue
            full_crc = checksums.crc64nvme(chunk, full_crc)
            part_crc = checksums.crc64nvme(chunk, part_crc)
            in_part += len(chunk)
            if in_part == part_size:
                part_crcs.append(_crc64_base64(part_crc))
                part_crc, in_part = 0, 0

    if read_total != size:
        raise LocalFileChangedError(
            f"File size changed while computing checksum: {path} "
            f"(expected {size}, read {read_total})"
        )

    sha256_b64 = base64.b64encode(sha256.digest()).decode("ascii")
    if part_size is None:
        return FileChecksums(sha256=sha256_b64)
    if in_part:
        part_crcs.append(_crc64_base64(part_crc))
    return FileChecksums(
        sha256=sha256_b64,
        part_size=part_size,
        part_crc64=tuple(part_crcs),
        crc64=_crc64_base64(full_crc),
    )


def _crc64_base64(value: int) -> str:
    return base64.b64encode(value.to_bytes(8, "big")).decode("ascii")
