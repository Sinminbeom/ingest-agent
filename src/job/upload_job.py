from python_library.job.job import IJob
from python_library.logger.app_logger import AppLogger
from python_library.storage.storage import IStorage
from python_library.storage.upload_options import UploadOptions

from job_container.request_container import RequestContainer


class UploadJob(IJob):
    def __init__(
        self,
        storage: IStorage,
        request_container: RequestContainer,
        meta_data_url: str,
        tenant_public_id: str,
        seq_id: str,
        batch_public_id: str,
        project_public_id: str,
        sample_public_id: str,
        file_kind: str,
        src_path: str,
        dst_path: str,
        dst_url: str,
    ):
        super().__init__()

        self.storage = storage
        self.request_container = request_container
        self.meta_data_url = meta_data_url
        self.tenant_public_id = tenant_public_id
        self.seq_id = seq_id
        self.batch_public_id = batch_public_id
        self.project_public_id = project_public_id
        self.sample_public_id = sample_public_id
        self.file_kind = file_kind
        self.src_path = src_path
        self.dst_path = dst_path
        self.dst_url = dst_url

    def execute(self) -> None:
        try:
            AppLogger.instance().info(
                f"Upload Start : seq_id = {self.seq_id}, batch_public_id = {self.batch_public_id}, project_public_id = {self.project_public_id}, sample_public_id = {self.sample_public_id}, file_kind = {self.file_kind}, src_path = {self.src_path}, dst_path = {self.dst_path}"
            )
            self.request_container.mark_file_detected(
                self.seq_id,
                self.batch_public_id,
                self.project_public_id,
                self.sample_public_id,
                self.file_kind,
                self.dst_url,
                self.tenant_public_id,
            )
            uploadOptions = UploadOptions(
                metadata={"metadata-uri": self.meta_data_url},
            )
            self.storage.upload(self.src_path, self.dst_path, uploadOptions)
            self.request_container.mark_file_uploaded(
                self.seq_id,
                self.batch_public_id,
                self.project_public_id,
                self.sample_public_id,
                self.file_kind,
                self.dst_url,
                self.tenant_public_id,
            )
            AppLogger.instance().info(
                f"Upload End : seq_id = {self.seq_id}, batch_public_id = {self.batch_public_id}, project_public_id = {self.project_public_id}, sample_public_id = {self.sample_public_id}, file_kind = {self.file_kind}, src_path = {self.src_path}, dst_path = {self.dst_path}"
            )
        except Exception as e:
            self.request_container.mark_file_failed(
                self.seq_id,
                self.batch_public_id,
                self.project_public_id,
                self.sample_public_id,
                self.file_kind,
                self.dst_url,
                "FAIL_UPLOAD",
                str(e),
                self.tenant_public_id,
            )
            AppLogger.instance().error(
                f"Upload failed : seq_id = {self.seq_id}, batch_public_id = {self.batch_public_id}, project_public_id = {self.project_public_id}, sample_public_id = {self.sample_public_id}, file_kind = {self.file_kind}, src_path = {self.src_path}, dst_path = {self.dst_path} \n {e}"
            )
