from oncx_core.db.db import IDB
from oncx_core.job.job import IJob
from oncx_core.logger.app_logger import AppLogger
from oncx_core.storage.storage import IStorage
from oncx_core.storage.upload_options import UploadOptions

from config.project_config import ProjectConfig
from job_container.request_container import RequestContainer


class UploadJob(IJob):
    def __init__(
        self,
        storage: IStorage,
        db: IDB,
        request_container: RequestContainer,
        meta_data_url: str,
        tenant_id: str,
        seq_id: str,
        batch_public_id: str,
        experiment_public_id: str,
        sample_public_id: str,
        src_path: str,
        dst_path: str,
        dst_url: str
    ):
        super().__init__()

        self.storage = storage
        self.db = db
        self.request_container = request_container
        self.meta_data_url = meta_data_url
        self.tenant_id = tenant_id
        self.seq_id = seq_id
        self.batch_public_id = batch_public_id
        self.experiment_public_id = experiment_public_id
        self.sample_public_id = sample_public_id
        self.src_path = src_path
        self.dst_path = dst_path
        self.dst_url = dst_url

    def execute(self) -> None:
        try:
            AppLogger.instance().info(
                f"Upload Start : seq_id = {self.seq_id}, batch_public_id = {self.batch_public_id}, experiment_public_id = {self.experiment_public_id}, sample_public_id = {self.sample_public_id}, src_path = {self.src_path}, dst_path = {self.dst_path}"
            )
            self.request_container.mark_file_detected(
                self.seq_id,
                self.batch_public_id,
                self.experiment_public_id,
                self.sample_public_id,
                self.dst_url,
                self.tenant_id,
            )
            uploadOptions = UploadOptions(
                metadata={"metadata-uri": self.meta_data_url},
            )
            self.running_file_upload()
            self.storage.upload(self.src_path, self.dst_path, uploadOptions)
            self.success_file_upload()
            self.request_container.mark_file_uploaded(
                self.seq_id,
                self.batch_public_id,
                self.experiment_public_id,
                self.sample_public_id,
                self.dst_url,
                self.tenant_id,
            )
            AppLogger.instance().info(
                f"Upload End : seq_id = {self.seq_id}, batch_public_id = {self.batch_public_id}, experiment_public_id = {self.experiment_public_id}, sample_public_id = {self.sample_public_id}, src_path = {self.src_path}, dst_path = {self.dst_path}"
            )
        except Exception as e:
            self.request_container.mark_file_failed(self.seq_id, self.batch_public_id, self.experiment_public_id, self.sample_public_id, self.dst_url, "FAIL_UPLOAD", str(e), self.tenant_id)
            self.fail_file_upload()
            AppLogger.instance().error(
                f"Upload failed : seq_id = {self.seq_id}, batch_public_id = {self.batch_public_id}, experiment_public_id = {self.experiment_public_id}, sample_public_id = {self.sample_public_id}, src_path = {self.src_path}, dst_path = {self.dst_path} \n {e}"
            )

    def running_file_upload(self):
        member_id = ProjectConfig.instance().member_id
        self.db.execute_update("""
            INSERT INTO registry.batch_file_upload (tenant_id, batch_id, experiment_file_id, local_file_path, status, created_by)
            SELECT b.tenant_id, b.id, ef.id, ef.local_file_path, 'UPLOADING', %s
            FROM registry.batch b
            JOIN registry.batch_detail bd ON bd.batch_id = b.id
            JOIN registry.experiment e ON bd.experiment_id = e.id
            JOIN registry.experiment_file ef ON ef.experiment_id = e.id
            WHERE b.public_id = %s::uuid
              AND e.public_id = %s::uuid
              AND ef.local_file_path = %s
            ON CONFLICT (batch_id, experiment_file_id)
            DO UPDATE SET status = 'UPLOADING', updated_by = %s, updated_at = NOW()
            """, (member_id, self.batch_public_id, self.experiment_public_id, self.src_path, member_id))
        self.db.commit()

    def success_file_upload(self):
        member_id = ProjectConfig.instance().member_id
        self.db.execute_update("""
            UPDATE registry.batch_file_upload bfu
            SET status = 'UPLOADED',
                s3_uri = %s,
                updated_by = %s,
                updated_at = NOW()
            FROM registry.batch b,
                 registry.experiment_file ef,
                 registry.experiment e
            WHERE bfu.batch_id = b.id
              AND bfu.experiment_file_id = ef.id
              AND ef.experiment_id = e.id
              AND b.public_id = %s::uuid
              AND e.public_id = %s::uuid
              AND bfu.local_file_path = %s
            """, (self.dst_url, member_id, self.batch_public_id, self.experiment_public_id, self.src_path))
        self.db.commit()

    def fail_file_upload(self):
        member_id = ProjectConfig.instance().member_id
        self.db.execute_update("""
            UPDATE registry.batch_file_upload bfu
            SET status = 'UPLOAD_FAILED',
                updated_by = %s,
                updated_at = NOW()
            FROM registry.batch b,
                 registry.experiment_file ef,
                 registry.experiment e
            WHERE bfu.batch_id = b.id
              AND bfu.experiment_file_id = ef.id
              AND ef.experiment_id = e.id
              AND b.public_id = %s::uuid
              AND e.public_id = %s::uuid
              AND bfu.local_file_path = %s
            """, (member_id, self.batch_public_id, self.experiment_public_id, self.src_path))
        self.db.commit()
