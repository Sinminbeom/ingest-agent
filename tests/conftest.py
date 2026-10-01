from __future__ import annotations

import os

import pytest
from python_library.logger.app_logger import AppLogger

from config.project_config import ProjectConfig
from upload.upload_plan import UploadFilePlan, UploadMode, UploadPartPlan
from upload.upload_state import BatchUploadState, FileUploadState

# 프로덕션 코드가 싱글턴 설정을 전제한다 — 테스트도 실제 conf로 초기화한다.
ProjectConfig.set_config("./conf/application.conf")
# 로그 폴더는 설치 프로그램·Docker 이미지가 미리 만든다. 빈 checkout(CI)에서도 같게 맞춘다.
os.makedirs("./logs", exist_ok=True)
AppLogger.set_config("./conf/logging.conf", "ingest-agent")


TENANT = "11111111-1111-4111-8111-111111111111"
BATCH = "22222222-2222-4222-8222-222222222222"
PROJECT = "33333333-3333-4333-8333-333333333333"
SAMPLE = "44444444-4444-4444-8444-444444444444"
SHA256 = "n4bQgYhMfWWaL+qgxVrQFaO/TxsrC4Is0V1sFbDwCgg="


def _single_plan(
    detail_file_public_id: str = "88888888-8888-4888-8888-000000000001",
    key: str = "k/single.raw",
) -> UploadFilePlan:
    return UploadFilePlan(
        detail_file_public_id=detail_file_public_id,
        key=key,
        mode=UploadMode.SINGLE,
        url="https://s3.test/single?sig",
        headers={"x-amz-checksum-sha256": SHA256},
    )


def _multipart_plan(
    part_count: int = 3,
    part_size: int = 10,
    detail_file_public_id: str = "88888888-8888-4888-8888-000000000002",
) -> UploadFilePlan:
    return UploadFilePlan(
        detail_file_public_id=detail_file_public_id,
        key="k/big.raw",
        mode=UploadMode.MULTIPART,
        checksum_algorithm="CRC64NVME",
        upload_id="upload-1",
        part_size=part_size,
        parts=[
            UploadPartPlan(
                part_number=n,
                url=f"https://s3.test/big?partNumber={n}",
                headers={"x-amz-checksum-crc64nvme": f"part{n}crc===="},
            )
            for n in range(1, part_count + 1)
        ],
        complete_url="https://s3.test/big?complete",
        complete_headers={
            "x-amz-checksum-crc64nvme": "fullcrc=====",
            "x-amz-checksum-type": "FULL_OBJECT",
            "x-amz-mp-object-size": str(part_size * (part_count - 1) + 5),
        },
        abort_url="https://s3.test/big?abort",
        list_parts_url="https://s3.test/big?list",
    )


def _file_state(
    plan: UploadFilePlan | None = None,
    src_path: str = "/data/S-001.raw",
    size_bytes: int = 10,
    file_kind: str = "SAMPLE",
) -> FileUploadState:
    plan = plan or _single_plan()
    sample = file_kind == "SAMPLE"
    return FileUploadState(
        plan=plan,
        src_path=src_path,
        size_bytes=size_bytes,
        sha256=SHA256,
        file_kind=file_kind,
        project_public_id=PROJECT if sample else None,
        sample_public_id=SAMPLE if sample else None,
        dst_url=f"s3://bucket/{plan.key}",
    )


def _batch_state(
    files: list[FileUploadState],
    expires_at: str = "2099-01-01T00:00:00Z",
    batch_public_id: str = BATCH,
    seq_id: str = "20260101000000_00000000",
) -> BatchUploadState:
    return BatchUploadState(
        tenant_public_id=TENANT,
        batch_public_id=batch_public_id,
        seq_id=seq_id,
        expires_at=expires_at,
        meta_json_url="https://s3.test/meta.json?X-Amz-Signature=secret",
        status_token="status-token",
        files=files,
    )


@pytest.fixture
def make_single_plan():
    return _single_plan


@pytest.fixture
def make_multipart_plan():
    return _multipart_plan


@pytest.fixture
def make_file_state():
    return _file_state


@pytest.fixture
def make_batch_state():
    return _batch_state
