from dataclasses import asdict
from typing import Any, Dict, List

from config.project_config import ProjectConfig
from job_container.composite_node import CompositeNode
from job_container.experiment_container import ExperimentContainer
from meta.batch import Batch, BatchIdentifiers, BatchContent, Source, Acquisition, Timestamps, Diagnostics
from utils.util import utc_now_iso


class BatchContainer(CompositeNode):
    """
    batch_public_id 단위 Composite.
    children = ExperimentContainer 들 (key: experiment_public_id)
    """

    def __init__(self, batch_public_id: str, tenant_id: str) -> None:
        super().__init__(batch_public_id)
        self.schema: str = ProjectConfig.instance().meta_schema_url

        project_name = ProjectConfig.instance().project_name
        project_version = ProjectConfig.instance().project_version

        software_name = ProjectConfig.instance().software_name
        software_version = ProjectConfig.instance().software_version

        mode_code = ProjectConfig.instance().mode_code
        mode_url = ProjectConfig.instance().mode_url

        self.batch = Batch(
            identifiers=BatchIdentifiers(tenant_uuid=tenant_id, batch_uuid=batch_public_id),
            content=BatchContent(
                source=Source(type="agent", name=project_name, version=project_version),
                acquisition=Acquisition(
                    software={"name": software_name, "version": software_version},
                    mode={"code": mode_code, "uri": mode_url},
                ),
            ),
            timestamps=Timestamps(),
            status="SUCCESS",
            diagnostics=Diagnostics(warnings=[], errors=[]),
            extensions={},
        )

    @property
    def batch_public_id(self) -> str:
        return self.name

    @property
    def experiments(self) -> Dict[str, ExperimentContainer]:
        return self._children # type: ignore[return-value]

    # -------- Experiment 헬퍼 --------
    def get_or_create_experiment(self, experiment_public_id: str) -> ExperimentContainer:
        node = self.get_child(experiment_public_id)
        if node is None:
            node = ExperimentContainer(experiment_public_id)
            self.add_child(experiment_public_id, node)
        return node  # type: ignore[return-value]

    def mark_requested(self) -> None:
        self.batch.timestamps.requested_at = utc_now_iso()

    def mark_ingested(self) -> None:
        self.batch.timestamps.ingested_at = utc_now_iso()

    def to_schema_dict(self) -> Dict[str, Any]:
        samples: List[Dict[str, Any]] = []
        for _, exp in self.iter_children():
            if not isinstance(exp, ExperimentContainer):
                continue
            for sample in exp.iter_sample_containers():
                samples.append(sample.to_schema_sample_dict())

        return {"$schema": self.schema, "batch": asdict(self.batch), "samples": samples}

    def to_dict(self) -> dict:
        return self.to_schema_dict()
