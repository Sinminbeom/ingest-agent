from __future__ import annotations

from typing import Dict, List

from job_container.composite_node import CompositeNode
from job_container.sample_container import SampleContainer


class ExperimentContainer(CompositeNode):
    """experiment_public_id 단위 Composite."""

    def __init__(self, experiment_public_id: str) -> None:
        super().__init__(experiment_public_id)

    @property
    def experiment_public_id(self) -> str:
        return self.name

    @property
    def samples(self) -> Dict[str, SampleContainer]:
        return self._children  # type: ignore[return-value]

    # -------- Sample 헬퍼 --------
    def get_or_create_sample(self, sample_public_id: str) -> SampleContainer:
        node = self.get_child(sample_public_id)
        if node is None:
            node = SampleContainer(self.experiment_public_id, sample_public_id)
            self.add_child(sample_public_id, node)
        return node  # type: ignore[return-value]

    def get_sample(self, sample_public_id: str) -> SampleContainer | None:
        node = self.get_child(sample_public_id)
        if isinstance(node, SampleContainer):
            return node
        return None

    def iter_sample_containers(self) -> List[SampleContainer]:
        out: List[SampleContainer] = []
        for _, node in self.iter_children():
            if isinstance(node, SampleContainer):
                out.append(node)
        return out
