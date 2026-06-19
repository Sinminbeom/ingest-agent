from datetime import datetime, timezone
import hashlib
import os
import base64


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def compute_sha256(file_path: str, chunk_size: int = 8192) -> str:
    sha256 = hashlib.sha256()

    with open(file_path, "rb") as f:
        for chunk in iter(lambda: f.read(chunk_size), b""):
            sha256.update(chunk)

    return sha256.hexdigest()


def compute_sha256_base64(file_path: str, chunk_size: int = 8192) -> str:
    sha256 = hashlib.sha256()

    with open(os.path.expanduser(file_path), "rb") as f:
        for chunk in iter(lambda: f.read(chunk_size), b""):
            sha256.update(chunk)

    return base64.b64encode(sha256.digest()).decode("utf-8")


def get_size_bytes(file_path: str) -> int:
    return os.path.getsize(file_path)
