import json

import pytest

import job.request_job as request_job_module
from job.request_job import RequestJob
from job_container.batch_container import BatchContainer
from upload.presigned_uploader import PresignedUploader
from upload.upload_errors import PermanentUploadError
from upload.upload_state_store import UploadStateStore


class StubApiServer:
    def __init__(self):
        self.statuses: list[str] = []

    def update_batch_status(self, batch_public_id, status):
        self.statuses.append(status)


class StubUploader(PresignedUploader):
    def __init__(self, error: Exception | None = None):
        self.error = error
        self.bodies: list[bytes] = []

    def upload_file(self, file_state, save_progress, resume=False):
        pass

    def put_bytes(self, url, data, content_type):
        self.bodies.append(data)
        if self.error is not None:
            raise self.error


class CapturingLogger:
    def __init__(self):
        self.errors: list[str] = []

    def error(self, msg):
        self.errors.append(msg)

    def info(self, msg):
        pass

    def warning(self, msg):
        pass


@pytest.fixture
def logger(monkeypatch):
    captured = CapturingLogger()
    monkeypatch.setattr(
        request_job_module.AppLogger, "instance", classmethod(lambda cls: captured)
    )
    return captured


@pytest.fixture
def finished_batch(
    tmp_path, make_file_state, make_single_plan, make_multipart_plan, make_batch_state
):
    ok = make_file_state(plan=make_single_plan(), src_path="/data/S-001.raw")
    ok.mark_detected()
    ok.mark_uploaded()
    failed = make_file_state(
        plan=make_multipart_plan(),
        src_path="/data/manifest.csv",
        file_kind="NON_SAMPLE",
    )
    failed.mark_detected()
    failed.mark_failed(
        "CHECKSUM_MISMATCH", "UploadPart part=2: HTTP 400 BadDigest", False
    )
    state = make_batch_state([ok, failed])

    container = BatchContainer(state.batch_public_id, state.tenant_public_id)
    for f in state.files:
        container.add_file(f)
        container.restore_file(f)

    store = UploadStateStore(str(tmp_path))
    store.save(state)
    return state, container, store


def _job(state, container, store, uploader, api_server, release=None) -> RequestJob:
    return RequestJob(
        container,
        api_server,
        uploader,
        None,  # type: ignore[arg-type]
        store,
        state,
        release=release or (lambda: None),
    )


def test_meta_failure_keeps_status_report_and_logs_full_json(finished_batch, logger):
    state, container, store = finished_batch
    api_server = StubApiServer()
    uploader = StubUploader(
        error=PermanentUploadError("PutBytes: HTTP 403 AccessDenied")
    )

    _job(state, container, store, uploader, api_server).execute()

    # meta.json 저장이 실패해도 파일 결과에 따른 배치 상태는 보고한다.
    assert api_server.statuses == ["FAILED"]
    assert store.load(state.batch_public_id) is None

    recovery = [m for m in logger.errors if m.startswith(RequestJob.META_RECOVERY_LOG)]
    assert len(recovery) == 1
    record = json.loads(recovery[0].removeprefix(RequestJob.META_RECOVERY_LOG + " "))
    assert record["batch_public_id"] == state.batch_public_id
    assert record["meta_json"] == json.loads(uploader.bodies[0])
    assert "AccessDenied" in record["error"]
    # 복구 로그에는 서명 쿼리와 상태 토큰을 넣지 않는다.
    assert record["destination"] == "https://s3.test/meta.json"
    assert "X-Amz-Signature" not in recovery[0]
    assert state.status_token not in recovery[0]


def test_failed_file_makes_failed_batch_with_file_error(finished_batch, logger):
    state, container, store = finished_batch
    uploader = StubUploader()

    _job(state, container, store, uploader, StubApiServer()).execute()

    meta = json.loads(uploader.bodies[0])
    assert meta["batch"]["status"] == "FAILED"
    files = [f for s in meta["samples"] for f in s["content"]["files"]]
    assert [f["status"] for f in files] == ["SUCCESS", "FAIL"]
    assert files[1]["diagnostics"]["error"]["code"] == "CHECKSUM_MISMATCH"


def test_confirmed_meta_json_is_reused_on_retry(finished_batch, logger):
    # 첫 시도에서 상태 보고가 실패해 상태 파일이 남은 뒤, 재개하면 같은 본문을 다시 쓴다.
    state, container, store = finished_batch

    class FailingOnce(StubApiServer):
        def update_batch_status(self, batch_public_id, status):
            super().update_batch_status(batch_public_id, status)
            raise RuntimeError("status report failed")

    first_uploader = StubUploader()
    _job(state, container, store, first_uploader, FailingOnce()).execute()
    reloaded = store.load(state.batch_public_id)
    assert reloaded is not None and reloaded.meta_json is not None

    second_uploader = StubUploader()
    api_server = StubApiServer()
    _job(reloaded, container, store, second_uploader, api_server).execute()

    assert second_uploader.bodies == first_uploader.bodies
    assert api_server.statuses == ["FAILED"]


def test_batch_is_released_even_when_finalize_fails(finished_batch, logger):
    # 상태 보고가 실패해도 배치를 놓아 줘야 사용자가 다시 시도할 수 있다(409가 계속 나지 않게).
    state, container, store = finished_batch

    class Failing(StubApiServer):
        def update_batch_status(self, batch_public_id, status):
            raise RuntimeError("status report failed")

    released = []
    _job(
        state, container, store, StubUploader(), Failing(), lambda: released.append(1)
    ).execute()

    assert released == [1]
    assert store.load(state.batch_public_id) is not None
