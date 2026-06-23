import time
import os
from typing import cast, List

from python_library.storage.s3.s3_storage_factory import S3StorageFactory
from python_library.storage.s3.s3_storage_info_factory import S3StorageInfoFactory
from python_library.storage.storage import IStorage
from python_library.thread.multi_thread_manager import MultiThreadManager

from app.job_complete_thread import JobCompleteThread
from app.job_worker_thread import JobWorkerThread
from aws.step_functions import StepFunctions
from config.project_config import ProjectConfig
from exceptions.file_not_found_exception import FileNotFoundException
from job.request_job import RequestJob
from job.upload_job import UploadJob
from job_container.request_container import RequestContainer
from job_container.sample_container import SampleContainer
from meta.api_server_client import ApiServerClient, FileInfo, StsCredentials
from utils.protocol_utils import ProtocolUtils


class IngestAgent(MultiThreadManager):
    INGEST_AGENT = "IngestAgent"

    def __init__(self):
        super().__init__()

        self._step_functions: StepFunctions = StepFunctions()
        self._request_container = RequestContainer()

        self._init_threads()

    def _init_threads(self) -> None:
        thread_count = ProjectConfig.instance().thread_count
        for _ in range(thread_count):
            self.append(JobWorkerThread())
        self.append(JobCompleteThread())

    def _create_storage(self, sts: StsCredentials) -> IStorage:
        storage_factory = S3StorageFactory(
            S3StorageInfoFactory(
                access_key=sts.access_key,
                secret_key=sts.secret_key,
                session_token=sts.session_token,
            )
        )
        storage = storage_factory.create_storage()
        storage.connect()
        return storage

    def upload(
        self,
        tenant_public_id: str,
        batch_public_id: str,
        token: str,
    ) -> None:
        api_server = ApiServerClient(
            base_url=ProjectConfig.instance().api_server_base_url,
            token=token,
            tenant_public_id=tenant_public_id,
        )
        result = api_server.get_batch_files(batch_public_id)
        file_info_list = result.files
        self._verify_local_files_exist(file_info_list)

        storage = self._create_storage(result.sts)

        seq_id = ProtocolUtils.instance().get_sequence_id_now()
        root_path = ProjectConfig.instance().root_path

        self.add_marker(
            file_info_list,
            root_path,
            tenant_public_id,
            seq_id,
            batch_public_id,
            storage,
        )
        self.push_upload_job(
            file_info_list,
            root_path,
            seq_id,
            tenant_public_id,
            batch_public_id,
            storage,
        )

        request_job = RequestJob(
            self._request_container,
            storage,
            api_server,
            self._step_functions,
            root_path,
            tenant_public_id,
            batch_public_id,
        )
        self.push_shared_queue(self.name, request_job)

    def _verify_local_files_exist(self, file_info_list: List[FileInfo]) -> None:
        missing_paths = [
            file_info.data_file_path
            for file_info in file_info_list
            if not os.path.isfile(file_info.data_file_path)
        ]
        if missing_paths:
            raise FileNotFoundException(missing_paths)

    def _dst_path(
        self,
        root_path: str,
        tenant_public_id: str,
        batch_public_id: str,
        file_info: FileInfo,
    ) -> str:
        file_name = os.path.basename(file_info.data_file_path)
        source = ProjectConfig.instance().source
        base = f"{root_path}tenant_public_id={tenant_public_id}/source={source}/batch_public_id={batch_public_id}"
        if file_info.file_kind == SampleContainer.KIND_SAMPLE:
            return f"{base}/project_public_id={file_info.project_public_id}/sample_public_id={file_info.sample_public_id}/{file_name}"
        return f"{base}/{file_name}"

    def _meta_json_path(
        self, root_path: str, tenant_public_id: str, batch_public_id: str
    ) -> str:
        source = ProjectConfig.instance().source
        return f"{root_path}tenant_public_id={tenant_public_id}/source={source}/batch_public_id={batch_public_id}/meta.json"

    def add_marker(
        self,
        file_info_list: List[FileInfo],
        root_path: str,
        tenant_public_id: str,
        seq_id: str,
        batch_public_id: str,
        storage: IStorage,
    ) -> None:
        for file_info in file_info_list:
            dst_path = self._dst_path(
                root_path, tenant_public_id, batch_public_id, file_info
            )
            dst_url = storage.to_url(dst_path)

            self._request_container.add_marker(
                seq_id,
                batch_public_id,
                file_info.project_public_id,
                file_info.sample_public_id,
                file_info.file_kind,
                dst_path,
                tenant_public_id,
            )
            self._request_container.add_file(
                seq_id,
                batch_public_id,
                file_info.project_public_id,
                file_info.sample_public_id,
                file_info.file_kind,
                file_info.data_file_path,
                dst_url,
            )

    def push_upload_job(
        self,
        file_info_list: List[FileInfo],
        root_path: str,
        seq_id: str,
        tenant_public_id: str,
        batch_public_id: str,
        storage: IStorage,
    ) -> None:
        meta_data_url = storage.to_url(
            self._meta_json_path(root_path, tenant_public_id, batch_public_id)
        )

        for file_info in file_info_list:
            dst_path = self._dst_path(
                root_path, tenant_public_id, batch_public_id, file_info
            )
            dst_url = storage.to_url(dst_path)

            upload_job = UploadJob(
                storage,
                self._request_container,
                meta_data_url,
                tenant_public_id,
                seq_id,
                batch_public_id,
                file_info.project_public_id,
                file_info.sample_public_id,
                file_info.file_kind,
                file_info.data_file_path,
                dst_path,
                dst_url,
            )
            self.push_shared_queue(JobWorkerThread.JOB_WORKER, upload_job)

    def action(self) -> None:
        while True:
            request_job = cast(RequestJob, self.pop_shared_queue(self.name))
            if request_job is not None:
                request_job.execute()
            time.sleep(0.001)
