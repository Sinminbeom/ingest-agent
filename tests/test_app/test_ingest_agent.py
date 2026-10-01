import threading
from pathlib import Path

import pytest

from app.ingest_agent import IngestAgent
from app.job_complete_thread import JobCompleteThread
from app.job_worker_thread import JobWorkerThread
from config.project_config import ProjectConfig

CONF_PATH = Path(__file__).resolve().parents[2] / "conf" / "application.conf"


class MarkJob:
    def __init__(self) -> None:
        self.executed = threading.Event()

    def execute(self) -> None:
        self.executed.set()


@pytest.fixture
def agent() -> IngestAgent:
    ProjectConfig.set_config(str(CONF_PATH))
    return IngestAgent()


def test_started_agent_runs_queued_jobs_and_stops_on_join(agent):
    # 종료 시 join이 끝나지 않던 회귀(#18). 대기 중인 스레드도 timeout 안에 빠져나와야 한다.
    agent_job = MarkJob()
    complete_job = MarkJob()

    agent.start()
    try:
        agent.push_shared_queue(agent.name, agent_job)
        agent.push_shared_queue(JobCompleteThread.JOB_COMPLETE, complete_job)
        assert agent_job.executed.wait(timeout=2)
        assert complete_job.executed.wait(timeout=2)
    finally:
        agent.stop()
        agent.join(timeout=JobWorkerThread.POP_TIMEOUT_SEC * 4)

    assert not agent.is_alive()
