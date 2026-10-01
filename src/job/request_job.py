import json
from typing import Any, Callable
from urllib.parse import urlsplit, urlunsplit

from python_library.job.job import IJob
from python_library.logger.app_logger import AppLogger

from aws.step_functions import StepFunctions
from job_container.batch_container import BatchContainer
from meta.api_server_client import ApiServerClient
from upload.presigned_uploader import PresignedUploader
from upload.upload_state import BatchUploadState
from upload.upload_state_store import UploadStateStore
from utils.util import utc_now_iso


class RequestJob(IJob):
    META_RECOVERY_LOG = "META_JSON_RECOVERY"

    def __init__(
        self,
        batch: BatchContainer,
        api_server: ApiServerClient,
        uploader: PresignedUploader,
        step_functions: StepFunctions,
        store: UploadStateStore,
        batch_state: BatchUploadState,
        release: Callable[[], None],
    ):
        super().__init__()
        self.batch = batch
        self.api_server = api_server
        self.uploader = uploader
        self.step_functions = step_functions
        self.store = store
        self.batch_state = batch_state
        self.batch_public_id = batch_state.batch_public_id
        self.release = release

    def execute(self) -> None:
        # 실패 시 상태 파일을 지우지 않는다 — 다음 기동 시 재개 흐름이
        # (모든 파일이 종결 상태면) 마무리 단계만 다시 수행한다.
        try:
            self._execute()
        except Exception as e:
            AppLogger.instance().error(
                f"Request finalize failed : batch_public_id = {self.batch_public_id} \n {e}"
            )
        finally:
            self.release()

    def _execute(self) -> None:
        meta_json = self.confirm_meta_json()
        self.write_meta_json(meta_json)
        self.set_batch_status(meta_json["batch"]["status"])
        self.store.delete(self.batch_public_id)
        self.start_execution()

    def confirm_meta_json(self) -> dict[str, Any]:
        # 저장 재시도·재개·복구 로그·상태 보고가 모두 같은 본문을 쓰도록 한 번만 만든다.
        if self.batch_state.meta_json is None:
            self.batch.mark_ingested()
            self.batch_state.meta_json = self.batch.to_schema_dict()
            self.store.save(self.batch_state)
        return self.batch_state.meta_json

    def write_meta_json(self, meta_json: dict[str, Any]) -> None:
        # 저장이 최종 실패해도 원본 결과 보고는 막지 않는다. 복구는 로그의 전체 JSON으로 한다.
        body = json.dumps(meta_json, ensure_ascii=False, indent=4).encode("utf-8")
        try:
            self.uploader.put_bytes(
                self.batch_state.meta_json_url, body, "application/json"
            )
        except Exception as e:
            self._log_meta_recovery(meta_json, e)

    def _log_meta_recovery(self, meta_json: dict[str, Any], error: Exception) -> None:
        # 서명이 든 쿼리는 빼고 저장 위치만 남긴다. 상태 토큰도 넣지 않는다.
        parts = urlsplit(self.batch_state.meta_json_url)
        destination = urlunsplit((parts.scheme, parts.netloc, parts.path, "", ""))
        record = {
            "tenant_public_id": self.batch_state.tenant_public_id,
            "batch_public_id": self.batch_public_id,
            "destination": destination,
            "failed_at": utc_now_iso(),
            "error": str(error),
            "meta_json": meta_json,
        }
        AppLogger.instance().error(
            f"{self.META_RECOVERY_LOG} {json.dumps(record, ensure_ascii=False)}"
        )

    def set_batch_status(self, status: str) -> None:
        self.api_server.update_batch_status(self.batch_public_id, status)

    def start_execution(self) -> None:
        pass
        # self.step_functions.start_execution(self.tenant_public_id, self.batch_public_id)
