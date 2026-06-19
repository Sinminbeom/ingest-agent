from dataclasses import asdict
from typing import Any, Dict, List

from config.project_config import ProjectConfig
from job_container.composite_node import CompositeNode
from job_container.sample_container import SampleContainer
from meta.batch import (
    Batch,
    BatchIdentifiers,
    BatchContent,
    Source,
    Acquisition,
    Timestamps,
    Diagnostics,
)
from utils.util import utc_now_iso


class BatchContainer(CompositeNode):
    """
    batch_public_id 단위 Composite.
    children = SampleContainer 들.
    - SAMPLE 파일: key = sample_public_id
    - NON_SAMPLE 파일: key = "" (단일 컨테이너에 모음)
    """

    NON_SAMPLE_KEY = ""

    def __init__(self, batch_public_id: str, tenant_public_id: str) -> None:
        super().__init__(batch_public_id)
        self.schema: str = ProjectConfig.instance().meta_schema_url

        project_name = ProjectConfig.instance().project_name
        project_version = ProjectConfig.instance().project_version

        software_name = ProjectConfig.instance().software_name
        software_version = ProjectConfig.instance().software_version

        mode_code = ProjectConfig.instance().mode_code
        mode_url = ProjectConfig.instance().mode_url

        self.batch = Batch(
            identifiers=BatchIdentifiers(
                tenant_uuid=tenant_public_id, batch_uuid=batch_public_id
            ),
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
    def samples(self) -> Dict[str, SampleContainer]:
        return self._children  # type: ignore[return-value]

    # -------- Sample 헬퍼 --------
    def get_or_create_sample(
        self, project_public_id: str, sample_public_id: str, file_kind: str
    ) -> SampleContainer:
        key = (
            sample_public_id
            if file_kind == SampleContainer.KIND_SAMPLE
            else BatchContainer.NON_SAMPLE_KEY
        )
        node = self.get_child(key)
        if node is None:
            node = SampleContainer(project_public_id, sample_public_id, file_kind)
            self.add_child(key, node)
        return node  # type: ignore[return-value]

    def iter_sample_containers(self) -> List[SampleContainer]:
        out: List[SampleContainer] = []
        for _, node in self.iter_children():
            if isinstance(node, SampleContainer):
                out.append(node)
        return out

    def has_failed_file(self) -> bool:
        return any(sc.has_failed_file() for sc in self.iter_sample_containers())

    def mark_requested(self) -> None:
        self.batch.timestamps.requested_at = utc_now_iso()

    def mark_ingested(self) -> None:
        self.batch.timestamps.ingested_at = utc_now_iso()

    def to_schema_dict(self) -> Dict[str, Any]:
        samples: List[Dict[str, Any]] = [
            sc.to_schema_sample_dict() for sc in self.iter_sample_containers()
        ]
        return {"$schema": self.schema, "batch": asdict(self.batch), "samples": samples}

    def to_dict(self) -> dict:
        return self.to_schema_dict()
