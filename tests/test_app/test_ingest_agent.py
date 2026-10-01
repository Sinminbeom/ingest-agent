import json
import threading
import time

import pytest

import app.ingest_agent as agent_module
from app.job_worker_thread import JobWorkerThread
from app.ingest_agent import IngestAgent
from exceptions.batch_already_running_exception import BatchAlreadyRunningException
from exceptions.project_access_denied_exception import ProjectAccessDeniedException
from meta.api_server_client import DetailFileInfo
from upload import upload_plan_request
from upload.presigned_uploader import PresignedUploader
from upload.upload_plan import UploadPlan
from upload.upload_state_store import UploadStateStore

TENANT = "11111111-1111-4111-8111-111111111111"
BATCH = "22222222-2222-4222-8222-222222222222"
PROJECT = "33333333-3333-4333-8333-333333333333"
SAMPLE = "44444444-4444-4444-8444-444444444444"
SAMPLE_FILE_ID = "88888888-8888-4888-8888-000000000001"
OTHER_FILE_ID = "88888888-8888-4888-8888-000000000002"


class StubApiServer:
    batches: dict[str, list[DetailFileInfo]] = {}
    plan_requests: list[list[dict]] = []
    # (batch_public_id, status, 보고에 쓴 토큰)
    statuses: list[tuple[str, str, str]] = []
    plan_error: Exception | None = None

    def __init__(self, base_url, token, tenant_public_id):
        self.token = token

    def get_batch_detail_files(self, batch_public_id):
        return StubApiServer.batches[batch_public_id]

    def update_batch_status(self, batch_public_id, status):
        StubApiServer.statuses.append((batch_public_id, status, self.token))

    def create_upload_plan(self, batch_public_id, files):
        if StubApiServer.plan_error is not None:
            raise StubApiServer.plan_error
        bodies = [f.to_api_dict() for f in files]
        StubApiServer.plan_requests.append(bodies)
        return UploadPlan.from_api_dict(
            {
                "expiresAt": "2099-01-01T00:00:00Z",
                "metaJsonUrl": "https://s3.test/meta.json?sig",
                "statusToken": "status-token",
                "files": [
                    {
                        "detailFilePublicId": b["detailFilePublicId"],
                        "key": f"k/{b['detailFilePublicId']}",
                        "mode": "SINGLE" if "partSize" not in b else "MULTIPART",
                        "headers": {"x-amz-checksum-sha256": b["sha256"]},
                        "parts": [],
                    }
                    for b in bodies
                ],
            }
        )


def _batch(files: list[DetailFileInfo]) -> list[DetailFileInfo]:
    return files


def _sample_file(path: str) -> DetailFileInfo:
    return DetailFileInfo(
        detail_file_public_id=SAMPLE_FILE_ID,
        project_public_id=PROJECT,
        sample_public_id=SAMPLE,
        data_file_path=path,
        file_kind="SAMPLE",
        is_masked=False,
    )


def _masked_file() -> DetailFileInfo:
    return DetailFileInfo(
        detail_file_public_id=OTHER_FILE_ID,
        project_public_id=None,
        sample_public_id=None,
        data_file_path=None,
        file_kind="SAMPLE",
        is_masked=True,
    )


@pytest.fixture
def store(tmp_path):
    return UploadStateStore(str(tmp_path / "state"))


class StubUploader(PresignedUploader):
    meta_bodies: list[bytes] = []

    def __init__(self):
        pass

    def upload_file(self, file_state, save_progress, resume=False):
        pass

    def put_bytes(self, url, data, content_type):
        StubUploader.meta_bodies.append(data)


@pytest.fixture
def stubs(monkeypatch, store):
    monkeypatch.setattr(agent_module, "ApiServerClient", StubApiServer)
    monkeypatch.setattr(agent_module, "PresignedUploader", StubUploader)
    monkeypatch.setattr(agent_module, "UploadStateStore", lambda: store)
    StubApiServer.batches = {}
    StubApiServer.plan_requests = []
    StubApiServer.statuses = []
    StubApiServer.plan_error = None
    StubUploader.meta_bodies = []


@pytest.fixture
def agent(store, stubs):
    # 스레드를 켜지 않는다. 대기열의 작업은 테스트가 직접 꺼내 실행한다.
    return IngestAgent()


def _queued_worker_jobs(agent: IngestAgent) -> int:
    return agent.size_shared_queue(JobWorkerThread.JOB_WORKER)


def _run_next_worker_job(agent: IngestAgent) -> None:
    job = agent.pop_shared_queue(JobWorkerThread.JOB_WORKER)
    assert job is not None
    job.execute()


def _run_all(agent: IngestAgent) -> None:
    while True:
        job = agent.pop_shared_queue(
            JobWorkerThread.JOB_WORKER
        ) or agent.pop_shared_queue(agent.name)
        if job is None:
            return
        job.execute()


def _statuses(batch_public_id: str) -> list[str]:
    return [s for b, s, _ in StubApiServer.statuses if b == batch_public_id]


@pytest.fixture
def raw_file(tmp_path):
    path = tmp_path / "run1" / "S-001.RAW"
    path.parent.mkdir()
    path.write_bytes(b"spectrum" * 100)
    return str(path)


def test_masked_file_stops_before_checksum_and_plan(
    agent, store, raw_file, monkeypatch
):
    StubApiServer.batches[BATCH] = _batch([_sample_file(raw_file), _masked_file()])
    computed = []
    monkeypatch.setattr(
        agent_module, "compute_checksums", lambda *a, **k: computed.append(a)
    )

    with pytest.raises(ProjectAccessDeniedException):
        agent.upload(TENANT, BATCH, "user-token")

    assert computed == []
    assert StubApiServer.plan_requests == []
    assert store.load(BATCH) is None
    assert _queued_worker_jobs(agent) == 0
    assert StubApiServer.statuses == []


def test_upload_plans_with_checksums_and_stores_meta_sources(agent, store, raw_file):
    StubApiServer.batches[BATCH] = _batch([_sample_file(raw_file)])

    agent.upload(TENANT, BATCH, "user-token")
    _run_next_worker_job(agent)

    [[body]] = StubApiServer.plan_requests
    assert set(body) == {"detailFilePublicId", "size", "sha256"}
    state = store.load(BATCH)
    assert state is not None
    [file] = state.files
    # 재개해도 다시 계산하지 않도록 계획에 보낸 체크섬을 진행 상태에 남긴다.
    assert file.sha256 == body["sha256"]
    assert _queued_worker_jobs(agent) == 1


def test_many_files_are_planned_in_several_requests(
    agent, store, tmp_path, monkeypatch
):
    monkeypatch.setattr(upload_plan_request, "MAX_FILES_PER_REQUEST", 2)
    files = []
    for n in range(5):
        path = tmp_path / f"f{n}.csv"
        path.write_text("a,b\n")
        files.append(
            DetailFileInfo(
                detail_file_public_id=f"88888888-8888-4888-8888-00000000010{n}",
                project_public_id=None,
                sample_public_id=None,
                data_file_path=str(path),
                file_kind="NON_SAMPLE",
                is_masked=False,
            )
        )
    StubApiServer.batches[BATCH] = _batch(files)

    agent.upload(TENANT, BATCH, "user-token")
    _run_next_worker_job(agent)

    assert [len(r) for r in StubApiServer.plan_requests] == [2, 2, 1]
    state = store.load(BATCH)
    assert state is not None
    assert [f.detail_file_public_id for f in state.files] == [
        f.detail_file_public_id for f in files
    ]


def _saved_state_with_failure(store, raw_file, fail_code: str, retryable: bool):
    # 이전 실행이 마무리 보고에 실패해 상태 파일만 남은 상황. 실행은 이미 끝나 있다.
    StubApiServer.batches[BATCH] = _batch([_sample_file(raw_file)])
    previous = IngestAgent()
    previous.upload(TENANT, BATCH, "user-token")
    _run_next_worker_job(previous)
    state = store.load(BATCH)
    assert state is not None
    state.files[0].mark_failed(fail_code, "failed", retryable)
    store.save(state)
    StubApiServer.plan_requests = []
    StubApiServer.statuses = []
    return state


def test_retrigger_after_checksum_mismatch_recomputes_from_scratch(
    agent, store, raw_file
):
    # 계산 뒤 원본이 바뀌면 옛 기대값으로는 계속 거절된다. 새로 계산해 새 계획을 받는다.
    old = _saved_state_with_failure(store, raw_file, "CHECKSUM_MISMATCH", False)
    with open(raw_file, "ab") as f:
        f.write(b"re-saved")

    agent.upload(TENANT, BATCH, "user-token")
    _run_next_worker_job(agent)

    [[body]] = StubApiServer.plan_requests
    assert body["sha256"] != old.files[0].sha256
    state = store.load(BATCH)
    assert state is not None
    assert state.files[0].sha256 == body["sha256"]


def test_retrigger_after_other_failure_resumes_existing_plan(agent, store, raw_file):
    old = _saved_state_with_failure(store, raw_file, "FAIL_UPLOAD_RETRYABLE", True)

    agent.upload(TENANT, BATCH, "user-token")

    assert _statuses(BATCH) == ["RUNNING"]
    assert StubApiServer.plan_requests == []
    state = store.load(BATCH)
    assert state is not None
    assert state.files[0].sha256 == old.files[0].sha256
    assert state.files[0].status == "PENDING"


def test_running_is_reported_before_responding_and_planning_runs_later(
    agent, store, raw_file
):
    # 체크섬 계산이 길어도 응답은 바로 나가고, 클라이언트는 RUNNING을 보고 폴링을 시작한다.
    StubApiServer.batches[BATCH] = _batch([_sample_file(raw_file)])

    agent.upload(TENANT, BATCH, "user-token")

    assert StubApiServer.statuses == [(BATCH, "RUNNING", "user-token")]
    assert StubApiServer.plan_requests == []
    assert store.load(BATCH) is None
    assert _queued_worker_jobs(agent) == 1

    _run_all(agent)

    # 끝 보고는 사용자 토큰이 만료돼도 되도록 status_token으로 한다.
    assert StubApiServer.statuses[1:] == [(BATCH, "SUCCESS", "status-token")]
    assert store.load(BATCH) is None


def test_same_batch_is_rejected_while_running(agent, raw_file):
    StubApiServer.batches[BATCH] = _batch([_sample_file(raw_file)])
    agent.upload(TENANT, BATCH, "user-token")

    with pytest.raises(BatchAlreadyRunningException):
        agent.upload(TENANT, BATCH, "user-token")

    assert _statuses(BATCH) == ["RUNNING"]
    _run_all(agent)
    agent.upload(TENANT, BATCH, "user-token")
    assert _statuses(BATCH) == ["RUNNING", "SUCCESS", "RUNNING"]


def test_planning_failure_after_response_reports_failed(agent, store, raw_file):
    StubApiServer.batches[BATCH] = _batch([_sample_file(raw_file)])
    StubApiServer.plan_error = RuntimeError("HTTP 401")
    agent.upload(TENANT, BATCH, "user-token")

    _run_all(agent)

    assert _statuses(BATCH) == ["RUNNING", "FAILED"]
    assert store.load(BATCH) is None
    # 실패한 배치는 다시 시도할 수 있다.
    StubApiServer.plan_error = None
    agent.upload(TENANT, BATCH, "user-token")


def test_batches_running_together_each_finish_with_own_result(agent, store, tmp_path):
    # 예전에는 먼저 끝난 배치가 공용 기록을 통째로 지워 다른 배치의 meta.json·상태 보고가 빠졌다.
    other_batch = "22222222-2222-4222-8222-222222222223"
    first = tmp_path / "a.raw"
    second = tmp_path / "b.raw"
    first.write_bytes(b"a" * 10)
    second.write_bytes(b"b" * 10)
    StubApiServer.batches[BATCH] = _batch([_sample_file(str(first))])
    StubApiServer.batches[other_batch] = _batch(
        [
            DetailFileInfo(
                detail_file_public_id=OTHER_FILE_ID,
                project_public_id=None,
                sample_public_id=None,
                data_file_path=str(second),
                file_kind="NON_SAMPLE",
                is_masked=False,
            )
        ]
    )

    agent.upload(TENANT, BATCH, "user-token")
    agent.upload(TENANT, other_batch, "user-token")
    _run_all(agent)

    assert _statuses(BATCH) == ["RUNNING", "SUCCESS"]
    assert _statuses(other_batch) == ["RUNNING", "SUCCESS"]
    written = [json.loads(b) for b in StubUploader.meta_bodies]
    assert sorted(m["batch"]["identifiers"]["batch_uuid"] for m in written) == [
        BATCH,
        other_batch,
    ]
    assert all(len(m["samples"]) == 1 for m in written)
    assert store.load(BATCH) is None and store.load(other_batch) is None


def test_startup_resume_with_all_files_done_finalizes_right_away(
    store, stubs, raw_file
):
    # 마무리 도중 꺼졌다면 올릴 파일이 없다. 업로드 잡 없이 바로 마무리만 한다.
    state = _saved_state_with_failure(store, raw_file, "FAIL_UPLOAD", False)
    state.files[0].reset_for_retry()
    state.files[0].mark_detected()
    state.files[0].mark_uploaded()
    store.save(state)

    agent = IngestAgent()
    agent.resume_incomplete_uploads()

    assert _queued_worker_jobs(agent) == 0
    _run_all(agent)
    assert _statuses(BATCH) == ["SUCCESS"]
    assert len(StubUploader.meta_bodies) == 1
    assert store.load(BATCH) is None


def test_started_agent_runs_queued_job_and_stops_on_join(agent):
    # 종료 시 join이 끝나지 않던 회귀(#18). 대기 중인 스레드도 timeout 안에 빠져나와야 한다.
    executed = threading.Event()

    class MarkJob:
        def execute(self):
            executed.set()

    agent.start()
    try:
        # 워커가 다 뜨기 전에 stop하면 늦게 뜬 워커의 start()가 stop 신호를 지운다(python-library).
        deadline = time.monotonic() + 2
        while not all(t.is_alive() for t in agent._threads):
            assert time.monotonic() < deadline
            time.sleep(0.01)
        agent.push_shared_queue(JobWorkerThread.JOB_WORKER, MarkJob())
        assert executed.wait(timeout=2)
    finally:
        agent.stop()
        agent.join(timeout=JobWorkerThread.POP_TIMEOUT_SEC * 4)

    assert not agent.is_alive()
