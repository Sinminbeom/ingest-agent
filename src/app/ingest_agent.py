import time
import os
from typing import cast, List, TypeAlias

from oncx_core.db.db import IDB
from oncx_core.db.postgresql.postgresql_db_factory import PostgresqlDBFactory
from oncx_core.db.postgresql.postgresql_db_info_factory import PostgresqlDBInfoFactory
from oncx_core.define.enum import IENUM
from oncx_core.logger.app_logger import AppLogger
from oncx_core.storage.s3.s3_storage_factory import S3StorageFactory
from oncx_core.storage.s3.s3_storage_info_factory import S3StorageInfoFactory
from oncx_core.storage.storage import IStorage
from oncx_core.thread.multi_thread_manager import MultiThreadManager

from app.job_complete_thread import JobCompleteThread
from app.job_worker_thread import JobWorkerThread
from aws.step_functions import StepFunctions
from config.aws_secrets_manager import AWSSecretsManager
from config.project_config import ProjectConfig
from job.request_job import RequestJob
from job.upload_job import UploadJob
from job_container.request_container import RequestContainer
from utils.protocol_utils import ProtocolUtils

FILE_INFO_TYPE: TypeAlias = tuple[str, str, str]


class IngestAgent(MultiThreadManager):
    INGEST_AGENT = "IngestAgent"

    class E_FILE_INFO(IENUM):
        EXPERIMENT_ID = 0
        SAMPLE_ID = 1
        FILE_PATH = 2

    def __init__(self):
        super().__init__()

        self._db: IDB | None = None
        self._storage: IStorage | None = None
        self._step_functions: StepFunctions | None = None

        self._init_db()
        self._init_storage()
        self._init_threads()
        self._init_step_functions()

        self._request_container = RequestContainer()

    def _init_threads(self):
        if self._db is None:
            raise ValueError("db is required")

        # JobWorkerThread
        thread_count = ProjectConfig.instance().thread_count
        for count in range(thread_count):
            self.append(JobWorkerThread())

        # JobComplete
        self.append(JobCompleteThread())

    def _init_db(self):
        db_secret = AWSSecretsManager.instance().load_db_config()
        port = ProjectConfig.instance().db_ssm_tunnel_port
        url = f"postgresql://127.0.0.1:{port}/{db_secret.dbname}?sslmode=require"
        db_factory = PostgresqlDBFactory(
            PostgresqlDBInfoFactory(url, db_secret.username, db_secret.password)
        )
        self._db = db_factory.create_db()
        self._db.connect()

    def _init_storage(self):
        storage_factory = S3StorageFactory(
            S3StorageInfoFactory()
        )
        self._storage = storage_factory.create_storage()
        self._storage.connect()

    def _init_step_functions(self):
        self._step_functions = StepFunctions()

    def upload(self, tenant_id: str, batch_public_id: str, member_public_id: str):
        if self._db is None:
            raise ValueError("db is required")

        if self._storage is None:
            raise ValueError("storage is required")

        member_id = self.resolve_member_id(member_public_id)
        ProjectConfig.instance().member_id = member_id

        seq_id = ProtocolUtils.instance().get_sequence_id_now()

        root_path = ProjectConfig.instance().root_path

        file_info_list = self.get_file_info_list(batch_public_id)

        self.add_marker(file_info_list, root_path, tenant_id, seq_id, batch_public_id)
        self.push_upload_job(file_info_list, root_path, seq_id, tenant_id, batch_public_id)

        request_job = RequestJob(self._request_container, self._storage, self._db, self._step_functions, root_path, tenant_id, batch_public_id)
        self.push_shared_queue(self.name, request_job)

    def resolve_member_id(self, member_public_id: str) -> int:
        if self._db is None:
            raise ValueError("db is required")
        rows = self._db.execute_query(
            "SELECT id FROM auth.member WHERE public_id = %s::uuid",
            (member_public_id,),
        )
        if not rows:
            from exceptions.custom_exception import CustomException
            from response.error_code import ErrorCode
            raise CustomException(ErrorCode.NOT_FOUND)
        return int(rows[0].get("id"))

    def add_marker(self, file_info_list: List[FILE_INFO_TYPE], root_path: str, tenant_id: str, seq_id: str, batch_public_id: str):
        for file_info in file_info_list:
            experiment_public_id = file_info[IngestAgent.E_FILE_INFO.EXPERIMENT_ID]
            sample_public_id = file_info[IngestAgent.E_FILE_INFO.SAMPLE_ID]
            file_path = file_info[IngestAgent.E_FILE_INFO.FILE_PATH]
            file_name = os.path.basename(file_path)

            if sample_public_id:
                dst_path = f"{root_path}{tenant_id}/{batch_public_id}/{experiment_public_id}/{sample_public_id}/{file_name}"
            else:
                dst_path = f"{root_path}{tenant_id}/{batch_public_id}/{experiment_public_id}/{file_name}"
            dst_url = self._storage.to_url(dst_path)

            self._request_container.add_marker(seq_id, batch_public_id, experiment_public_id, sample_public_id, dst_path, tenant_id)
            self._request_container.add_file(seq_id, batch_public_id, experiment_public_id, sample_public_id, file_path, dst_url)

    def push_upload_job(self, file_info_list: List[FILE_INFO_TYPE], root_path: str, seq_id: str, tenant_id: str, batch_public_id: str):
        for file_info in file_info_list:
            experiment_public_id = file_info[IngestAgent.E_FILE_INFO.EXPERIMENT_ID]
            sample_public_id = file_info[IngestAgent.E_FILE_INFO.SAMPLE_ID]
            file_path = file_info[IngestAgent.E_FILE_INFO.FILE_PATH]
            file_name = os.path.basename(file_path)

            meta_data_url = self._storage.to_url(f"{root_path}{tenant_id}/{batch_public_id}/meta.json")

            if sample_public_id:
                dst_path = f"{root_path}{tenant_id}/{batch_public_id}/{experiment_public_id}/{sample_public_id}/{file_name}"
            else:
                dst_path = f"{root_path}{tenant_id}/{batch_public_id}/{experiment_public_id}/{file_name}"
            dst_url = self._storage.to_url(dst_path)

            upload_job = UploadJob(
                self._storage,
                self._db,
                self._request_container,
                meta_data_url,
                tenant_id,
                seq_id,
                batch_public_id,
                experiment_public_id,
                sample_public_id,
                file_path,
                dst_path,
                dst_url
            )

            self.push_shared_queue(JobWorkerThread.JOB_WORKER, upload_job)

    def get_file_info_list(self, batch_public_id: str) -> List[FILE_INFO_TYPE]:
        if self._db is None:
            raise ValueError("db is required")

        all_files: List[FILE_INFO_TYPE] = list()

        db_rows = self._db.execute_query(
            """
            SELECT
                e.public_id AS experiment_public_id,
                s.public_id  AS sample_public_id,
                ef.local_file_path
            FROM registry.batch b
            JOIN registry.batch_detail bd ON bd.batch_id = b.id AND bd.tenant_id = b.tenant_id
            JOIN registry.experiment e ON e.id = bd.experiment_id
            JOIN registry.experiment_file ef ON ef.experiment_id = bd.experiment_id
            LEFT JOIN registry.sample s ON s.id = ef.sample_id
            WHERE b.public_id = %s::uuid
            """,
            (batch_public_id,)
        )
        for row in db_rows:
            experiment_public_id = str(row.get("experiment_public_id"))
            sample_public_id = str(row.get("sample_public_id") or "")
            file_path = str(row.get("local_file_path"))

            all_files.append((experiment_public_id, sample_public_id, file_path))

        return all_files

    def action(self) -> None:
        while True:
            request_job = cast(RequestJob, self.pop_shared_queue(self.name))
            if request_job is not None:
                request_job.execute()

            time.sleep(0.001)
