import os
from threading import Lock
from typing import Dict, List, Set, cast

from python_library.logger.app_logger import AppLogger
from python_library.thread.multi_thread_manager import MultiThreadManager

from app.job_worker_thread import JobWorkerThread
from aws.step_functions import StepFunctions
from config.project_config import ProjectConfig
from exceptions.batch_already_running_exception import BatchAlreadyRunningException
from exceptions.file_not_found_exception import FileNotFoundException
from exceptions.project_access_denied_exception import ProjectAccessDeniedException
from job.plan_job import PlanJob
from job.request_job import RequestJob
from job.upload_job import UploadJob
from job_container.batch_container import BatchContainer
from meta.api_server_client import ApiServerClient, DetailFileInfo
from upload.file_checksum import LocalFileChangedError, compute_checksums
from upload.presigned_uploader import PresignedUploader
from upload.upload_plan import UploadPlan
from upload.upload_plan_request import (
    UploadPlanFileRequest,
    part_size_for,
    split_requests,
)
from upload.upload_state import BatchUploadState, FileUploadState
from upload.upload_state_store import UploadStateStore
from utils.protocol_utils import ProtocolUtils


class IngestAgent(MultiThreadManager):
    INGEST_AGENT = "IngestAgent"
    BATCH_STATUS_RUNNING = "RUNNING"
    POP_TIMEOUT_SEC = 0.5

    def __init__(self):
        super().__init__()

        self._step_functions: StepFunctions = StepFunctions()
        self._store = UploadStateStore()
        self._uploader = PresignedUploader()
        self._running: Set[str] = set()
        self._running_lock = Lock()

        self._init_threads()

    def _init_threads(self) -> None:
        thread_count = ProjectConfig.instance().thread_count
        for _ in range(thread_count):
            self.append(JobWorkerThread())

    def upload(
        self,
        tenant_public_id: str,
        batch_public_id: str,
        token: str,
    ) -> None:
        self._acquire(batch_public_id)
        try:
            self._begin_upload(tenant_public_id, batch_public_id, token)
        except Exception:
            self._release(batch_public_id)
            raise

    def _begin_upload(
        self,
        tenant_public_id: str,
        batch_public_id: str,
        token: str,
    ) -> None:
        # 체크섬 계산처럼 오래 걸리는 일은 응답 뒤로 미룬다. 클라이언트는 RUNNING을 보고 폴링한다.
        api_server = ApiServerClient(
            base_url=ProjectConfig.instance().api_server_base_url,
            token=token,
            tenant_public_id=tenant_public_id,
        )

        batch_state = self._store.load(batch_public_id)
        # 체크섬 불일치는 원본이 바뀌었을 수 있어 기존 기대값으로 이어올리면 계속 거절된다.
        if (
            batch_state is not None
            and not batch_state.is_expired()
            and not batch_state.has_checksum_mismatch()
        ):
            # 같은 배치 재트리거 — 기존 플랜으로 이어올린다. 사용자가 명시적으로
            # 다시 시도한 것이므로 영구 실패 파일도 재시도 대상에 포함한다.
            AppLogger.instance().info(
                f"Resume upload (re-trigger) : batch_public_id = {batch_public_id}"
            )
            api_server.update_batch_status(batch_public_id, self.BATCH_STATUS_RUNNING)
            batch_state.reset_failed_for_retry(include_permanent=True)
            self._store.save(batch_state)
            self._start_batch(batch_state, resume=True)
            return

        if batch_state is not None:
            # 플랜 만료 또는 체크섬 불일치 — 기존 계획으로는 이어올릴 수 없다. 새 플랜으로
            # 처음부터 올린다. 고아 멀티파트 파트는 버킷 lifecycle 규칙(7일)이 정리한다.
            AppLogger.instance().warning(
                f"Upload plan unusable (expired or checksum mismatch), restarting from scratch : batch_public_id = {batch_public_id}"
            )
            self._store.delete(batch_public_id)

        detail_files = api_server.get_batch_detail_files(batch_public_id)
        # 권한 부족은 파일을 읽기 전에 알린다. 가려진 행은 경로도 비어 있다.
        if any(f.is_masked for f in detail_files):
            raise ProjectAccessDeniedException()
        self._verify_local_files_exist(detail_files)

        api_server.update_batch_status(batch_public_id, self.BATCH_STATUS_RUNNING)
        self.push_shared_queue(
            JobWorkerThread.JOB_WORKER,
            PlanJob(
                plan_and_start=lambda: self._plan_and_start(
                    api_server,
                    tenant_public_id,
                    batch_public_id,
                    detail_files,
                ),
                on_failed=lambda e: self._fail_planning(api_server, batch_public_id, e),
            ),
        )

    def _plan_and_start(
        self,
        api_server: ApiServerClient,
        tenant_public_id: str,
        batch_public_id: str,
        detail_files: List[DetailFileInfo],
    ) -> None:
        plan_requests = self._build_plan_requests(detail_files)
        plan = UploadPlan.merge(
            [
                api_server.create_upload_plan(batch_public_id, group)
                for group in split_requests(plan_requests)
            ]
        )

        seq_id = ProtocolUtils.instance().get_sequence_id_now()
        batch_state = self._build_batch_state(
            tenant_public_id,
            batch_public_id,
            seq_id,
            detail_files,
            plan_requests,
            plan,
        )
        self._store.save(batch_state)
        self._start_batch(batch_state, resume=False)

    def _fail_planning(
        self, api_server: ApiServerClient, batch_public_id: str, error: Exception
    ) -> None:
        # 응답은 이미 나갔다. 클라이언트가 폴링으로 알 수 있게 상태로 알린다.
        AppLogger.instance().error(
            f"Upload planning failed : batch_public_id = {batch_public_id} \n {error}"
        )
        try:
            api_server.update_batch_status(
                batch_public_id, BatchContainer.STATUS_FAILED
            )
        except Exception as e:
            AppLogger.instance().error(
                f"Status report failed : batch_public_id = {batch_public_id} \n {e}"
            )
        finally:
            self._release(batch_public_id)

    def resume_incomplete_uploads(self) -> None:
        """기동 시 미완료 배치를 이어올린다 — 절전·재시작·강제 종료 복구 경로.

        플랜(URL)과 status_token이 상태 파일에 있어 api-server 재호출 없이
        업로드 완주·meta.json·상태 보고까지 마칠 수 있다.
        """
        for batch_state in self._store.load_all():
            if batch_state.is_expired():
                # 재플랜에는 사용자 토큰이 필요해 여기서는 불가 — 사용자가 해당
                # 배치를 다시 트리거하면 새 플랜으로 다시 시작된다.
                AppLogger.instance().warning(
                    f"Incomplete upload abandoned (plan expired) : batch_public_id = {batch_state.batch_public_id}"
                )
                self._store.delete(batch_state.batch_public_id)
                continue
            AppLogger.instance().info(
                f"Resume upload (startup) : batch_public_id = {batch_state.batch_public_id}"
            )
            self._acquire(batch_state.batch_public_id)
            batch_state.reset_failed_for_retry(include_permanent=False)
            self._store.save(batch_state)
            self._start_batch(batch_state, resume=True)

    def _acquire(self, batch_public_id: str) -> None:
        with self._running_lock:
            if batch_public_id in self._running:
                raise BatchAlreadyRunningException()
            self._running.add(batch_public_id)

    def _release(self, batch_public_id: str) -> None:
        with self._running_lock:
            self._running.discard(batch_public_id)

    def _verify_local_files_exist(self, detail_files: List[DetailFileInfo]) -> None:
        missing_paths = [
            detail_file.data_file_path or ""
            for detail_file in detail_files
            if not detail_file.data_file_path
            or not os.path.isfile(detail_file.data_file_path)
        ]
        if missing_paths:
            raise FileNotFoundException(missing_paths)

    def _build_plan_requests(
        self, detail_files: List[DetailFileInfo]
    ) -> List[UploadPlanFileRequest]:
        requests: List[UploadPlanFileRequest] = []
        for detail_file in detail_files:
            path = cast(str, detail_file.data_file_path)
            size = os.path.getsize(path)
            try:
                checksums = compute_checksums(path, size, part_size_for(size))
            except (ValueError, LocalFileChangedError) as e:
                raise ValueError(f"Checksum failed: {path} ({e})") from e
            requests.append(
                UploadPlanFileRequest(
                    detail_file_public_id=detail_file.detail_file_public_id,
                    size=size,
                    checksums=checksums,
                )
            )
        return requests

    def _build_batch_state(
        self,
        tenant_public_id: str,
        batch_public_id: str,
        seq_id: str,
        detail_files: List[DetailFileInfo],
        plan_requests: List[UploadPlanFileRequest],
        plan: UploadPlan,
    ) -> BatchUploadState:
        # 객체 키는 서버가 확정한다(플랜 서명 대상) — agent는 경로를 만들지 않는다.
        bucket = ProjectConfig.instance().s3_bucket
        plans_by_id = {p.detail_file_public_id: p for p in plan.files}
        requests_by_id: Dict[str, UploadPlanFileRequest] = {
            r.detail_file_public_id: r for r in plan_requests
        }

        file_states: List[FileUploadState] = []
        for detail_file in detail_files:
            file_plan = plans_by_id.get(detail_file.detail_file_public_id)
            if file_plan is None:
                raise ValueError(
                    f"Upload plan missing for detail file: {detail_file.detail_file_public_id}"
                )
            request = requests_by_id[detail_file.detail_file_public_id]
            file_states.append(
                FileUploadState(
                    plan=file_plan,
                    src_path=cast(str, detail_file.data_file_path),
                    size_bytes=request.size,
                    sha256=request.checksums.sha256,
                    file_kind=detail_file.file_kind,
                    project_public_id=detail_file.project_public_id,
                    sample_public_id=detail_file.sample_public_id,
                    dst_url=f"s3://{bucket}/{file_plan.key}",
                )
            )

        return BatchUploadState(
            tenant_public_id=tenant_public_id,
            batch_public_id=batch_public_id,
            seq_id=seq_id,
            expires_at=plan.expires_at,
            meta_json_url=plan.meta_json_url,
            status_token=plan.status_token,
            files=file_states,
        )

    def _start_batch(self, batch_state: BatchUploadState, resume: bool) -> None:
        batch = self._build_container(batch_state, resume)
        batch.mark_requested()
        batch_state.mark_requested()
        self._store.save(batch_state)

        def finalize() -> None:
            self.push_shared_queue(self.name, self._request_job(batch, batch_state))

        pending_files = batch_state.pending_files()
        # 재개할 때 모든 파일이 이미 끝났으면 마지막 파일을 알릴 업로드 잡이 없다.
        if not pending_files:
            finalize()
            return

        for file_state in pending_files:
            upload_job = UploadJob(
                self._uploader,
                self._store,
                batch,
                batch_state,
                file_state,
                on_batch_uploaded=finalize,
                resume=resume,
            )
            self.push_shared_queue(JobWorkerThread.JOB_WORKER, upload_job)

    def _request_job(
        self, batch: BatchContainer, batch_state: BatchUploadState
    ) -> RequestJob:
        # 상태 보고는 status_token으로 한다— 업로드가 사용자
        # 토큰 수명(1시간)을 넘겨도, 재시작 후 재개돼도 완료 보고까지 가능하다.
        api_server = ApiServerClient(
            base_url=ProjectConfig.instance().api_server_base_url,
            token=batch_state.status_token,
            tenant_public_id=batch_state.tenant_public_id,
        )
        return RequestJob(
            batch,
            api_server,
            self._uploader,
            self._step_functions,
            self._store,
            batch_state,
            release=lambda: self._release(batch_state.batch_public_id),
        )

    def _build_container(
        self, batch_state: BatchUploadState, resume: bool
    ) -> BatchContainer:
        batch = BatchContainer(
            batch_state.batch_public_id, batch_state.tenant_public_id
        )
        if resume:
            batch.restore_requested_at(batch_state.requested_at)

        for file_state in batch_state.files:
            batch.add_marker(file_state.detail_file_public_id)
            batch.add_file(file_state)
            if resume:
                batch.restore_file(file_state)
                # 종결 파일은 업로드 잡이 다시 돌지 않으므로 마커도 완료 처리한다.
                if file_state.is_terminal:
                    batch.mark_complete(file_state.detail_file_public_id)
        return batch

    def action(self) -> None:
        while not self.is_stop():
            request_job = cast(
                RequestJob, self.pop_shared_queue(self.name, self.POP_TIMEOUT_SEC)
            )
            if request_job is not None:
                request_job.execute()
