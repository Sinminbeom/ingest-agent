from typing import cast

from python_library.job.job import IJob
from python_library.thread.queue_thread import QueueThread


class JobWorkerThread(QueueThread):
    JOB_WORKER = "JobWorker"
    POP_TIMEOUT_SEC = 0.5

    def __init__(self) -> None:
        super().__init__(JobWorkerThread.JOB_WORKER)

    def action(self) -> None:
        while not self.is_stop():
            job = cast(IJob, self.pop_shared_queue(self.name, self.POP_TIMEOUT_SEC))
            if job is None:
                continue

            job.execute()
