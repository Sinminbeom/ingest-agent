import pytest

from job.upload_job import UploadJob
from job_container.batch_container import BatchContainer
from meta.sample import File
from upload.presigned_uploader import PresignedUploader
from upload.upload_errors import (
    ChecksumMismatchError,
    PermanentUploadError,
    RetryableUploadError,
)
from upload.upload_state import FileUploadStatus
from upload.upload_state_store import UploadStateStore


class StubUploader(PresignedUploader):
    def __init__(self, error: Exception | None = None):
        self.error = error
        self.calls = 0

    def upload_file(self, file_state, save_progress, resume=False):
        self.calls += 1
        if self.error is not None:
            raise self.error


def _container(state) -> BatchContainer:
    # 업로드 시작 흐름과 같이 배치의 모든 파일을 먼저 등록한다.
    batch = BatchContainer(state.batch_public_id, state.tenant_public_id)
    for file in state.files:
        batch.add_marker(file.detail_file_public_id)
        batch.add_file(file)
    return batch


def _job(uploader, store, container, state, file, on_batch_uploaded=None) -> UploadJob:
    return UploadJob(
        uploader,
        store,
        container,
        state,
        file,
        on_batch_uploaded=on_batch_uploaded or (lambda: None),
    )


@pytest.fixture
def env(tmp_path, make_file_state, make_batch_state):
    file = make_file_state()
    state = make_batch_state([file])
    container = _container(state)
    store = UploadStateStore(str(tmp_path))
    return state, file, container, store, container.file(file.detail_file_public_id)


class TestUploadJobExecute:
    def test_success_marks_uploaded_and_persists(self, env):
        state, file, container, store, meta_file = env
        uploader = StubUploader()

        _job(uploader, store, container, state, file).execute()

        assert uploader.calls == 1
        assert file.status == FileUploadStatus.UPLOADED
        persisted = store.load(state.batch_public_id)
        assert persisted is not None
        assert persisted.files[0].status == FileUploadStatus.UPLOADED
        assert meta_file.status == File.E_FILE_STATUS.SUCCESS
        assert meta_file.timestamps.uploaded_at == file.uploaded_at

    def test_retryable_failure_is_marked_retryable(self, env):
        state, file, container, store, meta_file = env
        uploader = StubUploader(error=RetryableUploadError("network down"))

        _job(uploader, store, container, state, file).execute()

        assert file.status == FileUploadStatus.FAILED
        assert file.fail_retryable is True
        assert file.fail_code == UploadJob.FAIL_UPLOAD_RETRYABLE
        assert meta_file.status == File.E_FILE_STATUS.FAIL
        assert meta_file.timestamps.uploaded_at is None

    def test_permanent_failure_is_marked_permanent(self, env):
        state, file, container, store, _ = env
        uploader = StubUploader(error=PermanentUploadError("signature mismatch"))

        _job(uploader, store, container, state, file).execute()

        assert file.status == FileUploadStatus.FAILED
        assert file.fail_retryable is False
        assert file.fail_code == UploadJob.FAIL_UPLOAD

    def test_checksum_mismatch_has_its_own_code(self, env):
        state, file, container, store, meta_file = env
        uploader = StubUploader(error=ChecksumMismatchError("BadDigest"))

        _job(uploader, store, container, state, file).execute()

        assert file.fail_code == UploadJob.CHECKSUM_MISMATCH
        assert meta_file.diagnostics.error is not None
        assert meta_file.diagnostics.error.code == UploadJob.CHECKSUM_MISMATCH

    def test_expired_plan_fails_before_upload(self, env, make_batch_state):
        _, file, container, store, _ = env
        state = make_batch_state([file], expires_at="2000-01-01T00:00:00Z")
        uploader = StubUploader()

        _job(uploader, store, container, state, file).execute()

        assert uploader.calls == 0
        assert file.status == FileUploadStatus.FAILED
        assert file.fail_retryable is False


def test_only_last_finished_file_notifies_batch(
    tmp_path, make_file_state, make_single_plan, make_multipart_plan, make_batch_state
):
    # 실패도 끝난 것이다. 성공·실패와 관계없이 배치의 마지막 파일에서 한 번만 알린다.
    ok = make_file_state(plan=make_single_plan(), src_path="/data/S-001.raw")
    bad = make_file_state(plan=make_multipart_plan(), src_path="/data/S-002.raw")
    state = make_batch_state([ok, bad])
    container = _container(state)
    store = UploadStateStore(str(tmp_path))
    notified = []

    def notify():
        notified.append(True)

    _job(StubUploader(), store, container, state, ok, notify).execute()
    assert notified == []

    failing = StubUploader(error=PermanentUploadError("signature mismatch"))
    _job(failing, store, container, state, bad, notify).execute()
    assert notified == [True]
