import time
from typing import cast

from python_library.thread.queue_thread import QueueThread

from app.job_complete_thread import JobCompleteThread
from job.complete_job import CompleteJob
from job.upload_job import UploadJob


class JobWorkerThread(QueueThread):
    JOB_WORKER = "JobWorker"

    def __init__(self) -> None:
        super().__init__(JobWorkerThread.JOB_WORKER)

    def action(self) -> None:
        while True:
            time.sleep(0.001)

            job = cast(UploadJob, self.pop_shared_queue(self.name))
            if job is None:
                continue

            job.execute()

            complete_job = CompleteJob(
                job.request_container,
                job.seq_id,
                job.batch_public_id,
                job.experiment_public_id,
                job.sample_public_id,
                job.dst_path,
            )
            self.push_shared_queue(JobCompleteThread.JOB_COMPLETE, complete_job)
