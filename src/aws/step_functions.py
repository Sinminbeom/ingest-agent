import boto3
import json
from datetime import datetime, timezone

from oncx_core.logger.app_logger import AppLogger

from config.project_config import ProjectConfig


class StepFunctions:
    SERVICE_NAME = "stepfunctions"

    def __init__(self) -> None:
        self._region_name: str
        self._state_machine_arn: str

        self._init_step_functions()

    def _init_step_functions(self) -> None:
        self._region_name = ProjectConfig.instance().region_name
        self._state_machine_arn = ProjectConfig.instance().state_machine_arn

        self._client = boto3.client(
            service_name=StepFunctions.SERVICE_NAME,
            region_name=self._region_name,
        )

    def start_execution(self, tenant_id: str, batch_id: str) -> None:
        payload = {
            "tenant_id": tenant_id,
            "batch_id": batch_id
        }

        execution_name = f"ingest-{payload['tenant_id'][:8]}-{payload['batch_id'][:8]}-{int(datetime.now(tz=timezone.utc).timestamp())}"

        self._client.start_execution(
            stateMachineArn=self._state_machine_arn,
            name=execution_name,
            input=json.dumps(payload)
        )

        AppLogger.instance().info(f"Step functions start execution {payload}")
