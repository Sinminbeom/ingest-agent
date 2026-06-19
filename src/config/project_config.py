import os
from enum import StrEnum

from python_library.configure.app_config import AppConfig

from config.version import resolve_version


class ProjectConfig(AppConfig):
    class E_CATE_TYPE(StrEnum):
        COMMON = "COMMON"
        ACQUISITION = "ACQUISITION"
        DEV = "DEV"
        PRD = "PRD"

    class E_CATE_ELE_COMMON(StrEnum):
        PROJECT_NAME = "PROJECT_NAME"
        THREAD_COUNT = "THREAD_COUNT"
        META_SCHEMA_URL = "META_SCHEMA_URL"
        REGION_NAME = "REGION_NAME"
        S3_SOURCE = "S3_SOURCE"

    class E_CATE_ELE_ACQUISITION(StrEnum):
        SOFTWARE_NAME = "SOFTWARE_NAME"
        SOFTWARE_VERSION = "SOFTWARE_VERSION"
        MODE_CODE = "MODE_CODE"
        MODE_URL = "MODE_URL"

    class E_CATE_ELE_ENV(StrEnum):
        COGNITO_USER_POOL_ID = "COGNITO_USER_POOL_ID"
        S3_BUCKET = "S3_BUCKET"
        STATE_MACHINE_ARN = "STATE_MACHINE_ARN"
        API_SERVER_BASE_URL = "API_SERVER_BASE_URL"

    def __init__(self):
        super().__init__()

        self.project_name: str = self.get_config(
            ProjectConfig.E_CATE_TYPE.COMMON,
            ProjectConfig.E_CATE_ELE_COMMON.PROJECT_NAME,
        )
        # 버전은 conf가 아니라 pyproject.toml(개발) / VERSION 파일(배포)에서 읽는다.
        # conf는 업데이트 시 보존되어 self-update 후 옛 버전이 박히는 문제가 있었다.
        self.project_version: str = resolve_version()
        self.thread_count: int = int(
            self.get_config(
                ProjectConfig.E_CATE_TYPE.COMMON,
                ProjectConfig.E_CATE_ELE_COMMON.THREAD_COUNT,
            )
        )
        self.meta_schema_url: str = self.get_config(
            ProjectConfig.E_CATE_TYPE.COMMON,
            ProjectConfig.E_CATE_ELE_COMMON.META_SCHEMA_URL,
        )
        self.region_name: str = self.get_config(
            ProjectConfig.E_CATE_TYPE.COMMON,
            ProjectConfig.E_CATE_ELE_COMMON.REGION_NAME,
        )
        # bronze 공통 파티션 규칙의 source= 값 (예: ingest_agent)
        self.source: str = self.get_config(
            ProjectConfig.E_CATE_TYPE.COMMON,
            ProjectConfig.E_CATE_ELE_COMMON.S3_SOURCE,
        )

        self.software_name: str = self.get_config(
            ProjectConfig.E_CATE_TYPE.ACQUISITION,
            ProjectConfig.E_CATE_ELE_ACQUISITION.SOFTWARE_NAME,
        )
        self.software_version: str = self.get_config(
            ProjectConfig.E_CATE_TYPE.ACQUISITION,
            ProjectConfig.E_CATE_ELE_ACQUISITION.SOFTWARE_VERSION,
        )
        self.mode_code: str = self.get_config(
            ProjectConfig.E_CATE_TYPE.ACQUISITION,
            ProjectConfig.E_CATE_ELE_ACQUISITION.MODE_CODE,
        )
        self.mode_url: str = self.get_config(
            ProjectConfig.E_CATE_TYPE.ACQUISITION,
            ProjectConfig.E_CATE_ELE_ACQUISITION.MODE_URL,
        )

        self.app_env: str = os.environ.get("APP_ENV", "dev")
        self._load_env_config()

    def _load_env_config(self) -> None:
        section = (
            ProjectConfig.E_CATE_TYPE.PRD
            if self.app_env == "prd"
            else ProjectConfig.E_CATE_TYPE.DEV
        )
        self.cognito_user_pool_id: str = self.get_config(
            section,
            ProjectConfig.E_CATE_ELE_ENV.COGNITO_USER_POOL_ID,
        )
        s3_bucket: str = self.get_config(
            section,
            ProjectConfig.E_CATE_ELE_ENV.S3_BUCKET,
        )
        self.s3_bucket: str = s3_bucket
        # source= 파티션은 tenant_public_id 하위에 오므로 root_path는 버킷까지만.
        self.root_path: str = f"/{s3_bucket}/"
        self.state_machine_arn: str = self.get_config(
            section,
            ProjectConfig.E_CATE_ELE_ENV.STATE_MACHINE_ARN,
        )
        self.api_server_base_url: str = self.get_config(
            section,
            ProjectConfig.E_CATE_ELE_ENV.API_SERVER_BASE_URL,
        )
