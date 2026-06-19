import time
import json

from python_library.job.job import IJob
from python_library.storage.storage import IStorage
from python_library.storage.upload_options import UploadOptions

from aws.step_functions import StepFunctions
from config.project_config import ProjectConfig
from job_container.request_container import RequestContainer
from meta.api_server_client import ApiServerClient


class RequestJob(IJob):
    def __init__(
        self,
        request_container: RequestContainer,
        storage: IStorage,
        api_server: ApiServerClient,
        step_functions: StepFunctions,
        root_path: str,
        tenant_public_id: str,
        batch_public_id: str,
    ):
        super().__init__()
        self.request_container = request_container
        self.storage = storage
        self.api_server = api_server
        self.step_functions = step_functions
        self.root_path = root_path
        self.tenant_public_id = tenant_public_id
        self.batch_public_id = batch_public_id

    def execute(self) -> None:
        self.request_container.mark_batch_requested(self.batch_public_id)
        self.set_batch_status("RUNNING")

        while True:
            if self.request_container.is_all_completed():
                self.request_container.mark_batch_ingested(self.batch_public_id)
                self.write_meta_json()
                self.finalize_batch_status()
                self.request_container.clear_all()
                self.start_execution()
                break

            time.sleep(0.001)

    def write_meta_json(self) -> None:
        meta_json = self.request_container.export_batch_schema_dict(self.batch_public_id)
        meta_json_bytes = json.dumps(meta_json, ensure_ascii=False, indent=4).encode("utf-8")
        source = ProjectConfig.instance().source
        self.storage.write(
            f"{self.root_path}tenant_public_id={self.tenant_public_id}/source={source}/batch_public_id={self.batch_public_id}/meta.json",
            meta_json_bytes,
            UploadOptions(),
        )

    def set_batch_status(self, status: str) -> None:
        self.api_server.update_batch_status(self.batch_public_id, status)

    def finalize_batch_status(self) -> None:
        batch = self.request_container.find_batch(self.batch_public_id)
        status = "FAILED" if batch.has_failed_file() else "SUCCESS"
        self.set_batch_status(status)

    def start_execution(self) -> None:
        pass
        # self.step_functions.start_execution(self.tenant_public_id, self.batch_public_id)
