from typing import Type, TypeVar
import boto3
from oncx_core.singleton.singleton import Singleton
from pydantic import BaseModel

from config.project_config import ProjectConfig
from schemas.secret import DBSecretResponse

T = TypeVar("T", bound=BaseModel)


class AWSSecretsManager(Singleton):
    def __init__(self) -> None:
        self._client = boto3.client("secretsmanager", region_name=ProjectConfig.instance().region_name)

    def _load(self, secret_id: str, model: Type[T]) -> T:
        resp = self._client.get_secret_value(SecretId=secret_id)
        return model.model_validate_json(resp["SecretString"])

    def load_db_config(self) -> DBSecretResponse:
        return self._load(
            ProjectConfig.instance().aws_db_secret_id,
            DBSecretResponse,
        )
