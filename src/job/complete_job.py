from oncx_core.job.job import IJob
from oncx_core.logger.app_logger import AppLogger

from job_container.request_container import RequestContainer


class CompleteJob(IJob):
    def __init__(
        self,
        request_container: RequestContainer,
        seq_id: str,
        batch_public_id: str,
        experiment_public_id: str,
        sample_public_id: str,
        path: str,
    ):
        super().__init__()
        self.request_container = request_container
        self.seq_id = seq_id
        self.batch_public_id = batch_public_id
        self.experiment_public_id = experiment_public_id
        self.sample_public_id = sample_public_id
        self.path = path

    def execute(self) -> None:
        self.request_container.mark_complete(
            self.seq_id, self.batch_public_id, self.experiment_public_id, self.sample_public_id, self.path
        )
        AppLogger.instance().info(
            f"Complete : seq_id = {self.seq_id}, batch_public_id = {self.batch_public_id}, experiment_public_id = {self.experiment_public_id}, sample_public_id = {self.sample_public_id}, path = {self.path}"
        )
