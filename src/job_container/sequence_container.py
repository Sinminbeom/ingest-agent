from __future__ import annotations

from typing import Dict, Iterable

from job_container.batch_container import BatchContainer
from job_container.composite_node import CompositeNode
from job_container.sample_container import SampleContainer
from utils.util import compute_sha256_base64, get_size_bytes


class SequenceContainer(CompositeNode):
    """최상위 루트. children = BatchContainer."""

    def __init__(self, seq_id: str) -> None:
        super().__init__(seq_id)

    @property
    def seq_id(self) -> str:
        return self.name

    @property
    def batches(self) -> Dict[str, BatchContainer]:
        return self._children  # type: ignore[return-value]

    def get_or_create_batch(self, batch_public_id: str, tenant_id: str = "") -> BatchContainer:
        node = self.get_child(batch_public_id)
        if node is None:
            node = BatchContainer(batch_public_id, tenant_id)
            self.add_child(batch_public_id, node)
        return node  # type: ignore[return-value]

    # -------- 상위 레벨에서 바로 "샘플의 Job" 조작하는 헬퍼 --------
    def _get_or_create_sample(self, batch_public_id: str, experiment_public_id: str, sample_public_id: str, tenant_id: str = "") -> SampleContainer:
        batch = self.get_or_create_batch(batch_public_id, tenant_id)
        experiment = batch.get_or_create_experiment(experiment_public_id)
        return experiment.get_or_create_sample(sample_public_id)

    def add_markers(self, batch_public_id: str, experiment_public_id: str, sample_public_id: str, markers: Iterable[str]) -> None:
        self._get_or_create_sample(batch_public_id, experiment_public_id, sample_public_id).add_markers(markers)

    def add_marker(self, batch_public_id: str, experiment_public_id: str, sample_public_id: str, marker: str, tenant_id: str = "") -> None:
        self._get_or_create_sample(batch_public_id, experiment_public_id, sample_public_id, tenant_id).add_marker(marker)

    def add_file(self, batch_public_id: str, experiment_public_id: str, sample_public_id: str, path: str, url: str) -> None:
        self._get_or_create_sample(batch_public_id, experiment_public_id, sample_public_id).add_file(url, get_size_bytes(path), "SHA256", compute_sha256_base64(path))

    def mark_complete(self, batch_public_id: str, experiment_public_id: str, sample_public_id: str, marker: str) -> None:
        self._get_or_create_sample(batch_public_id, experiment_public_id, sample_public_id).mark_complete(marker)

    def is_marker_done(self, batch_public_id: str, experiment_public_id: str, sample_public_id: str, marker: str) -> bool:
        return self._get_or_create_sample(batch_public_id, experiment_public_id, sample_public_id).is_marker_done(marker)
