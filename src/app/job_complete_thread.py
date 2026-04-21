import time

from oncx_core.thread.worker_thread import abWorkerThread


class JobCompleteThread(abWorkerThread):
    JOB_COMPLETE = "JobComplete"

    def __init__(self):
        super().__init__(JobCompleteThread.JOB_COMPLETE)

    def action(self) -> None:
        while True:
            time.sleep(0.001)

            job = self.pop_shared_queue(self.name)
            if job is None:
                continue

            job.execute()
