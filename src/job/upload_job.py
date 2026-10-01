from typing import Callable

from python_library.job.job import IJob
from python_library.logger.app_logger import AppLogger

from job_container.batch_container import BatchContainer
from upload.presigned_uploader import PresignedUploader
from upload.upload_errors import (
    ChecksumMismatchError,
    PermanentUploadError,
    RetryableUploadError,
    UploadError,
)
from upload.upload_state import BatchUploadState, FileUploadState
from upload.upload_state_store import UploadStateStore


class UploadJob(IJob):
    # meta.json samples[].content.files[].diagnostics.error.code — 재시도 가능/영구 실패/체크섬 불일치를 구분한다.
    FAIL_UPLOAD = UploadError.CODE
    FAIL_UPLOAD_RETRYABLE = RetryableUploadError.CODE
    CHECKSUM_MISMATCH = ChecksumMismatchError.CODE

    def __init__(
        self,
        uploader: PresignedUploader,
        store: UploadStateStore,
        batch: BatchContainer,
        batch_state: BatchUploadState,
        file_state: FileUploadState,
        on_batch_uploaded: Callable[[], None],
        resume: bool = False,
    ):
        super().__init__()

        self.uploader = uploader
        self.store = store
        self.batch = batch
        self.batch_state = batch_state
        self.file_state = file_state
        self.on_batch_uploaded = on_batch_uploaded
        self.resume = resume

    @property
    def seq_id(self) -> str:
        return self.batch_state.seq_id

    @property
    def batch_public_id(self) -> str:
        return self.batch_state.batch_public_id

    @property
    def detail_file_public_id(self) -> str:
        return self.file_state.detail_file_public_id

    def _log_context(self) -> str:
        return (
            f"seq_id = {self.seq_id}, batch_public_id = {self.batch_public_id}, "
            f"detail_file_public_id = {self.detail_file_public_id}, "
            f"src_path = {self.file_state.src_path}, dst_url = {self.file_state.dst_url}"
        )

    def execute(self) -> None:
        try:
            self._upload()
        finally:
            if self.batch.complete_file(self.detail_file_public_id):
                self.on_batch_uploaded()

    def _upload(self) -> None:
        try:
            AppLogger.instance().info(f"Upload Start : {self._log_context()}")
            self.file_state.mark_detected()
            self.store.save(self.batch_state)
            self.batch.mark_file_detected(self.detail_file_public_id)
            if self.batch_state.is_expired():
                raise PermanentUploadError(
                    f"Upload plan expired at {self.batch_state.expires_at}"
                )
            self.uploader.upload_file(
                self.file_state,
                save_progress=lambda: self.store.save(self.batch_state),
                resume=self.resume,
            )
            self.file_state.mark_uploaded()
            self.store.save(self.batch_state)
            self.batch.mark_file_uploaded(
                self.detail_file_public_id, self.file_state.uploaded_at or ""
            )
            AppLogger.instance().info(f"Upload End : {self._log_context()}")
        except Exception as e:
            retryable = isinstance(e, UploadError) and e.retryable
            code = self._fail_code(e, retryable)
            # meta.json 오류 메시지는 비어 있으면 안 된다.
            msg = str(e) or type(e).__name__
            self.file_state.mark_failed(code, msg, retryable)
            self.store.save(self.batch_state)
            self.batch.mark_file_failed(
                self.detail_file_public_id, code, msg, self.file_state.fail_at
            )
            AppLogger.instance().error(
                f"Upload failed : {self._log_context()}, retryable = {retryable} \n {e}"
            )

    @classmethod
    def _fail_code(cls, e: Exception, retryable: bool) -> str:
        if isinstance(e, ChecksumMismatchError):
            return cls.CHECKSUM_MISMATCH
        return cls.FAIL_UPLOAD_RETRYABLE if retryable else cls.FAIL_UPLOAD
