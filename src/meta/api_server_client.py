from dataclasses import dataclass
from typing import List

import httpx


@dataclass(frozen=True)
class FileInfo:
    project_public_id: str
    sample_public_id: str
    data_file_path: str
    file_kind: str


@dataclass(frozen=True)
class StsCredentials:
    access_key: str
    secret_key: str
    session_token: str


@dataclass(frozen=True)
class BatchFilesResult:
    sts: StsCredentials
    files: List[FileInfo]


class ApiServerClient:
    def __init__(self, base_url: str, token: str, tenant_public_id: str) -> None:
        self._base_url = base_url
        self._token = token
        self._tenant_public_id = tenant_public_id

    def _headers(self) -> dict:
        return {
            "Authorization": f"Bearer {self._token}",
            "X-Tenant-Id": self._tenant_public_id,
        }

    def get_batch_files(self, batch_public_id: str) -> BatchFilesResult:
        response = httpx.get(
            f"{self._base_url}/batches/{batch_public_id}/files",
            headers=self._headers(),
        )
        response.raise_for_status()
        # 서버는 ApiResponse envelope({timestamp, status, data})로 감싸고
        # 바디 키는 camelCase로 내려준다. data를 언래핑하고 camelCase로 읽는다.
        data = response.json()["data"]
        sts_data = data["sts"]
        sts = StsCredentials(
            access_key=sts_data["accessKey"],
            secret_key=sts_data["secretKey"],
            session_token=sts_data["sessionToken"],
        )
        files = [
            FileInfo(
                project_public_id=str(item.get("projectPublicId") or ""),
                sample_public_id=str(item.get("samplePublicId") or ""),
                data_file_path=str(item.get("dataFilePath") or ""),
                file_kind=str(item["fileKind"]),
            )
            for item in data["files"]
        ]
        return BatchFilesResult(sts=sts, files=files)

    def update_batch_status(self, batch_public_id: str, status: str) -> None:
        response = httpx.patch(
            f"{self._base_url}/batches/{batch_public_id}/status",
            headers=self._headers(),
            json={"status": status},
        )
        response.raise_for_status()
