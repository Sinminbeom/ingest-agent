import time
import json

from oncx_core.db.db import IDB
from oncx_core.job.job import IJob
from oncx_core.storage.storage import IStorage
from oncx_core.storage.upload_options import UploadOptions

from aws.step_functions import StepFunctions
from config.project_config import ProjectConfig
from job_container.request_container import RequestContainer


class RequestJob(IJob):
    def __init__(
        self, request_container: RequestContainer, storage: IStorage, db: IDB, step_functions: StepFunctions, root_path: str, tenant_id: str, batch_public_id: str
    ):
        super().__init__()
        self.request_container = request_container
        self.db = db
        self.storage = storage
        self.step_functions = step_functions
        self.root_path = root_path
        self.tenant_id = tenant_id
        self.batch_public_id = batch_public_id

    def execute(self) -> None:
        self.request_container.mark_batch_requested(self.batch_public_id)
        self.running_batch_db()

        # 하나의 요청이 끝날때 까지 기다림
        while True:
            # 하나의 요청이 끝나면 break
            if self.request_container.is_all_completed():
                self.request_container.mark_batch_ingested(self.batch_public_id)
                self.write_meta_json()
                self.update_batch_status_from_details()
                self.request_container.clear_all()
                self.start_execution()
                break

            time.sleep(0.001)

    def write_meta_json(self):
        meta_json = self.request_container.export_batch_schema_dict(self.batch_public_id)

        meta_json_bytes = json.dumps(meta_json, ensure_ascii=False, indent=4).encode('utf-8')
        self.storage.write(f"{self.root_path}{self.tenant_id}/{self.batch_public_id}/meta.json", meta_json_bytes, UploadOptions())

    def running_batch_db(self) -> None:
        member_id = ProjectConfig.instance().member_id
        self.db.execute_update("""
            UPDATE registry.batch
            SET status = 'RUNNING',
                updated_by = %s,
                updated_at = NOW()
            WHERE public_id = %s::uuid
        """, (member_id, self.batch_public_id))
        self.db.commit()

    def update_batch_status_from_details(self) -> None:
        member_id = ProjectConfig.instance().member_id
        self.db.execute_update("""
            UPDATE registry.batch b
            SET status = s.new_status,
                updated_by = %s,
                updated_at = NOW()
            FROM (
              SELECT
                bfu.batch_id,
                CASE
                  WHEN bool_or(bfu.status IN ('UPLOAD_FAILED', 'UPLOADING'))
                    THEN 'FAILED'::registry.batch_status
                  WHEN bool_and(bfu.status = 'UPLOADED')
                    THEN 'SUCCESS'::registry.batch_status
                  ELSE
                    'IDLE'::registry.batch_status
                END AS new_status
              FROM registry.batch b2
              JOIN registry.batch_file_upload bfu ON bfu.batch_id = b2.id
              WHERE b2.public_id = %s::uuid
              GROUP BY bfu.batch_id
            ) s
            WHERE b.id = s.batch_id
        """, (member_id, self.batch_public_id))
        self.db.commit()

    def start_execution(self):
        pass
        # self.step_functions.start_execution(self.tenant_id, self.batch_public_id)
