from __future__ import annotations

import time
from typing import Callable, Iterator

import httpx

from python_library.logger.app_logger import AppLogger

from upload.multipart_xml import MultipartXml
from upload.upload_errors import (
    ChecksumMismatchError,
    PermanentUploadError,
    RetryableUploadError,
)
from upload.upload_plan import UploadMode
from upload.upload_state import FileUploadState


class PresignedUploader:
    """프리사인드 URL 대상 HTTP PUT 업로더.

    boto3 고수준 API(upload_file)를 쓰지 않으므로 SDK가 해주던 파트 분할·ETag
    수집·CompleteMultipartUpload 조립·재시도를 직접 수행한다. AWS 자격증명은
    일절 다루지 않는다 — 서명은 URL에 이미 들어 있다.

    파트 전송은 파일 내에서 순차다. 기존 정책(UploadOptions.max_concurrency=1)과
    동일하며, 병렬성은 파일 단위(JobWorkerThread 수)로 유지된다.
    """

    MAX_ATTEMPTS = 5
    BACKOFF_BASE_SECONDS = 1.0
    BACKOFF_CAP_SECONDS = 60.0
    RETRYABLE_STATUSES = frozenset({408, 429, 500, 502, 503, 504})
    # CompleteMultipartUpload는 HTTP 200 바디로도 에러를 내려준다.
    RETRYABLE_S3_CODES = frozenset({"InternalError", "SlowDown", "RequestTimeout"})
    # 체크섬 불일치(BadDigest)는 같은 기대값으로 이 횟수까지만 보낸다(처음 포함).
    MAX_DIGEST_ATTEMPTS = 3
    BAD_DIGEST = "BadDigest"
    READ_CHUNK_SIZE = 1024 * 1024
    CONNECT_TIMEOUT_SECONDS = 60.0
    IO_TIMEOUT_SECONDS = 600.0

    def __init__(self, client: httpx.Client | None = None) -> None:
        # httpx.Client는 스레드 세이프 — 워커 스레드들이 공유한다.
        self._client = client or httpx.Client(
            timeout=httpx.Timeout(
                connect=self.CONNECT_TIMEOUT_SECONDS,
                read=self.IO_TIMEOUT_SECONDS,
                write=self.IO_TIMEOUT_SECONDS,
                pool=self.CONNECT_TIMEOUT_SECONDS,
            )
        )

    # -------- 공개 API --------
    def upload_file(
        self,
        file_state: FileUploadState,
        save_progress: Callable[[], None],
        resume: bool = False,
    ) -> None:
        if file_state.plan.mode == UploadMode.SINGLE:
            self._upload_single(file_state)
        else:
            self._upload_multipart(file_state, save_progress, resume)

    def put_bytes(self, url: str, data: bytes, content_type: str) -> None:
        """작은 페이로드(meta.json 등)를 프리사인드 URL로 PUT한다."""
        self._send_with_retry(
            lambda: self._client.put(
                url, content=data, headers={"Content-Type": content_type}
            ),
            operation="PutBytes",
        )

    def list_parts(self, list_parts_url: str) -> dict[int, str]:
        """S3가 실제 보관한 파트 번호 -> ETag. 응답 유실 파트의 ETag 회수용."""
        response = self._send_with_retry(
            lambda: self._client.get(list_parts_url),
            operation="ListParts",
        )
        return MultipartXml.parse_list_parts(response.content)

    # -------- 전송 --------
    def _upload_single(self, file_state: FileUploadState) -> None:
        url = file_state.plan.url
        if not url:
            raise PermanentUploadError("SINGLE plan has no url")
        # 단일 PUT은 원자적 — 파트 개념이 없어 실패 시 처음부터 다시 보낸다.
        headers = {
            **file_state.plan.headers,
            "Content-Length": str(file_state.size_bytes),
        }
        self._send_until_digest_matches(
            lambda: self._client.put(
                url,
                content=self._iter_file_range(
                    file_state.src_path, 0, file_state.size_bytes
                ),
                headers=headers,
            ),
            operation=f"PutObject key={file_state.plan.key}",
        )

    def _upload_multipart(
        self,
        file_state: FileUploadState,
        save_progress: Callable[[], None],
        resume: bool,
    ) -> None:
        plan = file_state.plan
        if plan.part_size is None or not plan.parts or not plan.complete_url:
            raise PermanentUploadError("MULTIPART plan is incomplete")

        if resume and plan.list_parts_url:
            if self._merge_remote_parts(file_state, save_progress):
                return

        for part_number in file_state.pending_part_numbers():
            etag = self._put_part(file_state, part_number)
            file_state.record_part(part_number, etag)
            save_progress()

        self._complete(file_state)

    def _merge_remote_parts(
        self, file_state: FileUploadState, save_progress: Callable[[], None]
    ) -> bool:
        """ListParts를 로컬 기록에 병합한다. 이미 complete된 업로드면 True.

        complete 성공 직후 상태 저장 전에 죽은 경우 uploadId가 사라져
        NoSuchUpload가 난다. agent는 abort를 호출하지 않고 lifecycle 정리(7일)는
        플랜 만료와 같은 창이므로, 로컬 기록상 전 파트가 완료된 NoSuchUpload는
        complete 완료로 판정한다.
        """
        try:
            listed = self.list_parts(file_state.plan.list_parts_url or "")
        except PermanentUploadError as e:
            if "NoSuchUpload" in str(e) and not file_state.pending_part_numbers():
                AppLogger.instance().warning(
                    f"Upload already completed (NoSuchUpload on ListParts) : key = {file_state.plan.key}"
                )
                return True
            raise
        file_state.merge_listed_parts(listed)
        save_progress()
        return False

    def _put_part(self, file_state: FileUploadState, part_number: int) -> str:
        plan = file_state.plan
        part_size = plan.part_size or 0
        offset = (part_number - 1) * part_size
        length = min(part_size, file_state.size_bytes - offset)
        if length <= 0:
            raise PermanentUploadError(
                f"Part out of range: part_number={part_number}, size={file_state.size_bytes}"
            )
        part = plan.part(part_number)
        headers = {**part.headers, "Content-Length": str(length)}
        response = self._send_until_digest_matches(
            lambda: self._client.put(
                part.url,
                content=self._iter_file_range(file_state.src_path, offset, length),
                headers=headers,
            ),
            operation=f"UploadPart key={plan.key}, part={part_number}",
            validate=self._validate_part_response,
        )
        return response.headers["ETag"]

    @staticmethod
    def _validate_part_response(response: httpx.Response) -> None:
        if not response.headers.get("ETag"):
            # ETag 없이는 complete를 조립할 수 없다. 파트 재전송으로 회복 가능.
            raise RetryableUploadError("No ETag in UploadPart response")

    def _complete(self, file_state: FileUploadState) -> None:
        xml_body = MultipartXml.build_complete(file_state.completed_etags)
        # 전체 CRC 불일치(BadDigest)는 조각이 모두 통과한 뒤라 다시 보내도 같아서 실패로 끝낸다.
        headers = {
            **file_state.plan.complete_headers,
            "Content-Type": "application/xml",
        }
        self._send_with_retry(
            lambda: self._client.post(
                file_state.plan.complete_url or "",
                content=xml_body,
                headers=headers,
            ),
            operation=f"CompleteMultipartUpload key={file_state.plan.key}",
            validate=self._validate_complete_response,
        )

    def _validate_complete_response(self, response: httpx.Response) -> None:
        error_code = MultipartXml.parse_error_code(response.content)
        if error_code is None:
            return
        message = f"CompleteMultipartUpload error: {error_code}"
        if error_code in self.RETRYABLE_S3_CODES:
            raise RetryableUploadError(message)
        if error_code == self.BAD_DIGEST:
            raise ChecksumMismatchError(message)
        raise PermanentUploadError(message)

    # -------- 재시도 공통 --------
    def _send_until_digest_matches(
        self,
        request: Callable[[], httpx.Response],
        operation: str,
        validate: Callable[[httpx.Response], None] | None = None,
    ) -> httpx.Response:
        for attempt in range(1, self.MAX_DIGEST_ATTEMPTS + 1):
            try:
                return self._send_with_retry(request, operation, validate)
            except ChecksumMismatchError as e:
                if attempt == self.MAX_DIGEST_ATTEMPTS:
                    raise
                AppLogger.instance().warning(
                    f"Checksum mismatch (attempt {attempt}/{self.MAX_DIGEST_ATTEMPTS}) : {operation} \n {e}"
                )
        raise AssertionError("unreachable")

    def _send_with_retry(
        self,
        request: Callable[[], httpx.Response],
        operation: str,
        validate: Callable[[httpx.Response], None] | None = None,
    ) -> httpx.Response:
        last_error: RetryableUploadError | None = None
        for attempt in range(self.MAX_ATTEMPTS):
            if attempt > 0:
                time.sleep(self._backoff_seconds(attempt))
            try:
                response = request()
                self._raise_for_status(response, operation)
                if validate is not None:
                    validate(response)
                return response
            except RetryableUploadError as e:
                last_error = e
                AppLogger.instance().warning(
                    f"Retryable upload failure (attempt {attempt + 1}/{self.MAX_ATTEMPTS}) : {operation} \n {e}"
                )
            except httpx.TransportError as e:
                last_error = RetryableUploadError(f"{operation}: {e!r}")
                AppLogger.instance().warning(
                    f"Transport failure (attempt {attempt + 1}/{self.MAX_ATTEMPTS}) : {operation} \n {e!r}"
                )
        raise last_error or RetryableUploadError(f"{operation}: retry exhausted")

    def _raise_for_status(self, response: httpx.Response, operation: str) -> None:
        if response.status_code < 400:
            return
        # S3 오류 본문에는 서명 계산 내용이 들어 있어 코드만 남긴다(로그·meta.json에 쓰임).
        error_code = MultipartXml.parse_error_code(response.content)
        detail = error_code or (response.text[:200] if response.content else "")
        message = f"{operation}: HTTP {response.status_code} {detail}".rstrip()
        if response.status_code in self.RETRYABLE_STATUSES:
            raise RetryableUploadError(message)
        if error_code == self.BAD_DIGEST:
            raise ChecksumMismatchError(message)
        # 4xx — 서명 불일치·만료·NoSuchUpload 등. 같은 요청 반복으로는 못 고친다.
        raise PermanentUploadError(message)

    def _backoff_seconds(self, attempt: int) -> float:
        return min(
            self.BACKOFF_CAP_SECONDS, self.BACKOFF_BASE_SECONDS * (2 ** (attempt - 1))
        )

    @classmethod
    def _iter_file_range(cls, path: str, offset: int, length: int) -> Iterator[bytes]:
        with open(path, "rb") as f:
            f.seek(offset)
            remaining = length
            while remaining > 0:
                chunk = f.read(min(cls.READ_CHUNK_SIZE, remaining))
                if not chunk:
                    # 업로드 도중 로컬 파일이 줄어든 경우 — 재시도 무의미.
                    raise PermanentUploadError(
                        f"Local file shrank during upload: {path}"
                    )
                remaining -= len(chunk)
                yield chunk
