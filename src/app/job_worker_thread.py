from typing import cast

from python_library.thread.queue_thread import QueueThread

from app.job_complete_thread import JobCompleteThread
from job.complete_job import CompleteJob
from job.upload_job import UploadJob


class JobWorkerThread(QueueThread):
    JOB_WORKER = "JobWorker"
    POP_TIMEOUT_SEC = 0.5

    def __init__(self) -> None:
        super().__init__(JobWorkerThread.JOB_WORKER)

    def action(self) -> None:
        while not self.is_stop():
            job = cast(
                UploadJob, self.pop_shared_queue(self.name, self.POP_TIMEOUT_SEC)
            )
            if job is None:
                continue

            job.execute()

            complete_job = CompleteJob(
                job.request_container,
                job.seq_id,
                job.batch_public_id,
                job.project_public_id,
                job.sample_public_id,
                job.file_kind,
                job.dst_path,
            )
            self.push_shared_queue(JobCompleteThread.JOB_COMPLETE, complete_job)
