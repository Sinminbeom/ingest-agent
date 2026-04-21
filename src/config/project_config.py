import os
from enum import StrEnum

from oncx_core.configure.app_config import AppConfig


class ProjectConfig(AppConfig):
    class E_CATE_TYPE(StrEnum):
        COMMON = "COMMON"
        ACQUISITION = "ACQUISITION"
        DEV = "DEV"
        PRD = "PRD"

    class E_CATE_ELE_COMMON(StrEnum):
        PROJECT_NAME = "PROJECT_NAME"
        PROJECT_VERSION = "PROJECT_VERSION"
        THREAD_COUNT = "THREAD_COUNT"
        META_SCHEMA_URL = "META_SCHEMA_URL"
        REGION_NAME = "REGION_NAME"
        S3_BASE_PATH = "S3_BASE_PATH"

    class E_CATE_ELE_ACQUISITION(StrEnum):
        SOFTWARE_NAME = "SOFTWARE_NAME"
        SOFTWARE_VERSION = "SOFTWARE_VERSION"
        MODE_CODE = "MODE_CODE"
        MODE_URL = "MODE_URL"

    class E_CATE_ELE_ENV(StrEnum):
        COGNITO_USER_POOL_ID = "COGNITO_USER_POOL_ID"
        AWS_DB_SECRET_ID = "AWS_DB_SECRET_ID"
        DB_SSM_TUNNEL_PORT = "DB_SSM_TUNNEL_PORT"
        S3_BUCKET = "S3_BUCKET"
        STATE_MACHINE_ARN = "STATE_MACHINE_ARN"

    def __init__(self):
        super().__init__()

        self.project_name: str = self.get_config(
            ProjectConfig.E_CATE_TYPE.COMMON,
            ProjectConfig.E_CATE_ELE_COMMON.PROJECT_NAME,
        )
        self.project_version: str = self.get_config(
            ProjectConfig.E_CATE_TYPE.COMMON,
            ProjectConfig.E_CATE_ELE_COMMON.PROJECT_VERSION,
        )
        self.thread_count: int = int(self.get_config(
            ProjectConfig.E_CATE_TYPE.COMMON,
            ProjectConfig.E_CATE_ELE_COMMON.THREAD_COUNT,
        ))
        self.meta_schema_url: str = self.get_config(
            ProjectConfig.E_CATE_TYPE.COMMON,
            ProjectConfig.E_CATE_ELE_COMMON.META_SCHEMA_URL,
        )
        self.region_name: str = self.get_config(
            ProjectConfig.E_CATE_TYPE.COMMON,
            ProjectConfig.E_CATE_ELE_COMMON.REGION_NAME,
        )
        self.s3_base_path: str = self.get_config(
            ProjectConfig.E_CATE_TYPE.COMMON,
            ProjectConfig.E_CATE_ELE_COMMON.S3_BASE_PATH,
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
        self.aws_db_secret_id: str = self.get_config(
            section,
            ProjectConfig.E_CATE_ELE_ENV.AWS_DB_SECRET_ID,
        )
        self.db_ssm_tunnel_port: int = int(self.get_config(
            section,
            ProjectConfig.E_CATE_ELE_ENV.DB_SSM_TUNNEL_PORT,
        ))
        s3_bucket: str = self.get_config(
            section,
            ProjectConfig.E_CATE_ELE_ENV.S3_BUCKET,
        )
        self.s3_bucket: str = s3_bucket
        self.root_path: str = f"/{s3_bucket}/{self.s3_base_path}/"
        self.state_machine_arn: str = self.get_config(
            section,
            ProjectConfig.E_CATE_ELE_ENV.STATE_MACHINE_ARN,
        )
