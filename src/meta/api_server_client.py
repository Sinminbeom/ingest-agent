from dataclasses import dataclass

import httpx

from upload.upload_plan import UploadPlan
from upload.upload_plan_request import UploadPlanFileRequest


@dataclass(frozen=True)
class DetailFileInfo:
    detail_file_public_id: str
    project_public_id: str | None
    sample_public_id: str | None
    data_file_path: str | None
    file_kind: str
    is_masked: bool


def _optional_str(value: object) -> str | None:
    return None if value is None else str(value)


class ApiServerClient:
    # upload-plan은 파일·파트 수에 비례해 프리사인드 URL을 일괄 서명하므로
    # 응답까지 오래 걸릴 수 있다 — 읽기 타임아웃을 넉넉히 잡는다.
    TIMEOUT = httpx.Timeout(connect=10.0, read=300.0, write=60.0, pool=10.0)

    def __init__(self, base_url: str, token: str, tenant_public_id: str) -> None:
        self._base_url = base_url
        self._token = token
        self._tenant_public_id = tenant_public_id

    def _headers(self) -> dict:
        return {
            "Authorization": f"Bearer {self._token}",
            "X-Tenant-Id": self._tenant_public_id,
        }

    def get_batch_detail_files(self, batch_public_id: str) -> list[DetailFileInfo]:
        response = httpx.get(
            f"{self._base_url}/batches/{batch_public_id}/with-detail-files",
            headers=self._headers(),
            timeout=ApiServerClient.TIMEOUT,
        )
        response.raise_for_status()
        # api-server는 ApiResponse envelope({timestamp, status, data})로 감싸고
        # 바디 키는 camelCase로 내려준다. data를 언래핑하고 camelCase로 읽는다.
        data = response.json()["data"]
        return [
            DetailFileInfo(
                detail_file_public_id=str(item["publicId"]),
                project_public_id=_optional_str(item.get("projectPublicId")),
                sample_public_id=_optional_str(item.get("samplePublicId")),
                data_file_path=_optional_str(item.get("dataFilePath")),
                file_kind=str(item["fileKind"]),
                is_masked=bool(item.get("isMasked", False)),
            )
            for item in data["detailFiles"]
        ]

    def create_upload_plan(
        self, batch_public_id: str, files: list[UploadPlanFileRequest]
    ) -> UploadPlan:
        # 요청 하나의 파일·URL 수 상한은 부르는 쪽이 지킨다(split_requests).
        response = httpx.post(
            f"{self._base_url}/batches/{batch_public_id}/upload-plan",
            headers=self._headers(),
            json={"files": [f.to_api_dict() for f in files]},
            timeout=ApiServerClient.TIMEOUT,
        )
        response.raise_for_status()
        return UploadPlan.from_api_dict(response.json()["data"])

    def update_batch_status(self, batch_public_id: str, status: str) -> None:
        response = httpx.patch(
            f"{self._base_url}/batches/{batch_public_id}/status",
            headers=self._headers(),
            json={"status": status},
            timeout=ApiServerClient.TIMEOUT,
        )
        response.raise_for_status()
