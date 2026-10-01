from __future__ import annotations


class UploadError(RuntimeError):
    """프리사인드 업로드 실패. retryable로 재시도 가능/영구 실패를 구분한다."""

    CODE = "FAIL_UPLOAD"

    def __init__(self, msg: str, retryable: bool) -> None:
        super().__init__(msg)
        self.retryable = retryable


class RetryableUploadError(UploadError):
    """일시 장애(네트워크 단절, 5xx, 429 등) — 재개 시 이어올릴 수 있다."""

    CODE = "FAIL_UPLOAD_RETRYABLE"

    def __init__(self, msg: str) -> None:
        super().__init__(msg, retryable=True)


class PermanentUploadError(UploadError):
    """같은 플랜으로 재시도해도 성공할 수 없는 실패(서명 불일치, 플랜 만료 등)."""

    def __init__(self, msg: str) -> None:
        super().__init__(msg, retryable=False)


class ChecksumMismatchError(PermanentUploadError):
    """BadDigest. 전송 중 손상이면 다시 보내 회복되지만, 원본이 바뀌었으면 계속 틀린다."""

    CODE = "CHECKSUM_MISMATCH"
