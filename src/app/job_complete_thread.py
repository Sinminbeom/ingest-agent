from python_library.thread.queue_thread import QueueThread


class JobCompleteThread(QueueThread):
    JOB_COMPLETE = "JobComplete"
    POP_TIMEOUT_SEC = 0.5

    def __init__(self):
        super().__init__(JobCompleteThread.JOB_COMPLETE)

    def action(self) -> None:
        while not self.is_stop():
            job = self.pop_shared_queue(self.name, self.POP_TIMEOUT_SEC)
            if job is None:
                continue

            job.execute()
