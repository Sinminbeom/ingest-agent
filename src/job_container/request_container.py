from typing import Dict, Iterable, Any

from job_container.batch_container import BatchContainer
from job_container.composite_node import CompositeNode
from job_container.sequence_container import SequenceContainer
from utils.util import utc_now_iso


class RequestContainer(CompositeNode):
    REQUEST_ROOT = "RequestRoot"
    """
    Request 단위의 최상위 루트.
    children = SequenceContainer 들 (key: seq_id)
    """

    def __init__(self) -> None:
        super().__init__(RequestContainer.REQUEST_ROOT)

    @property
    def sequences(self) -> Dict[str, SequenceContainer]:
        return self._children  # type: ignore[return-value]

    def get_or_create_sequence(self, seq: str) -> SequenceContainer:
        node = self.get_child(seq)
        if node is None:
            node = SequenceContainer(seq)
            self.add_child(seq, node)
        return node  # type: ignore[return-value]

    # ---- 기존 API 유지 ----
    def add_markers(
        self,
        seq: str,
        batch_public_id: str,
        project_public_id: str,
        sample_public_id: str,
        file_kind: str,
        markers: Iterable[str],
    ) -> None:
        self.get_or_create_sequence(seq).add_markers(
            batch_public_id, project_public_id, sample_public_id, file_kind, markers
        )

    def add_marker(
        self,
        seq: str,
        batch_public_id: str,
        project_public_id: str,
        sample_public_id: str,
        file_kind: str,
        marker: str,
        tenant_public_id: str = "",
    ) -> None:
        self.get_or_create_sequence(seq).add_marker(
            batch_public_id,
            project_public_id,
            sample_public_id,
            file_kind,
            marker,
            tenant_public_id,
        )

    def add_file(
        self,
        seq: str,
        batch_public_id: str,
        project_public_id: str,
        sample_public_id: str,
        file_kind: str,
        path: str,
        url: str,
    ) -> None:
        self.get_or_create_sequence(seq).add_file(
            batch_public_id, project_public_id, sample_public_id, file_kind, path, url
        )

    def mark_complete(
        self,
        seq: str,
        batch_public_id: str,
        project_public_id: str,
        sample_public_id: str,
        file_kind: str,
        marker: str,
    ) -> None:
        self.get_or_create_sequence(seq).mark_complete(
            batch_public_id, project_public_id, sample_public_id, file_kind, marker
        )

    def is_marker_done(
        self,
        seq: str,
        batch_public_id: str,
        project_public_id: str,
        sample_public_id: str,
        file_kind: str,
        marker: str,
    ) -> bool:
        return self.get_or_create_sequence(seq).is_marker_done(
            batch_public_id, project_public_id, sample_public_id, file_kind, marker
        )

    def mark_batch_requested(self, batch_public_id: str) -> None:
        for _, seq in self.iter_children():
            for _, batch in seq.iter_children():
                if (
                    isinstance(batch, BatchContainer)
                    and batch.batch_public_id == batch_public_id
                ):
                    batch.batch.timestamps.requested_at = utc_now_iso()
                    return

        raise ValueError(f"Batch not found: batch_public_id={batch_public_id}")

    def mark_batch_ingested(self, batch_public_id: str) -> None:
        for _, seq in self.iter_children():  # SequenceContainer들
            for _, batch in seq.iter_children():  # BatchContainer들
                if (
                    isinstance(batch, BatchContainer)
                    and batch.batch_public_id == batch_public_id
                ):
                    batch.batch.timestamps.ingested_at = utc_now_iso()
                    return

        raise ValueError(f"Batch not found: batch_public_id={batch_public_id}")

    def find_batch(self, batch_public_id: str) -> BatchContainer:
        for _, seq in self.iter_children():
            for _, batch in seq.iter_children():
                if (
                    isinstance(batch, BatchContainer)
                    and batch.batch_public_id == batch_public_id
                ):
                    return batch
        raise ValueError(f"Batch not found: batch_public_id={batch_public_id}")

    def mark_file_detected(
        self,
        seq_id: str,
        batch_public_id: str,
        project_public_id: str,
        sample_public_id: str,
        file_kind: str,
        path: str,
        tenant_public_id: str = "",
    ) -> None:
        seq = self.get_or_create_sequence(seq_id)
        batch = seq.get_or_create_batch(batch_public_id, tenant_public_id)
        sample = batch.get_or_create_sample(
            project_public_id, sample_public_id, file_kind
        )
        sample.mark_file_detected(path)

    def mark_file_uploaded(
        self,
        seq_id: str,
        batch_public_id: str,
        project_public_id: str,
        sample_public_id: str,
        file_kind: str,
        path: str,
        tenant_public_id: str = "",
    ) -> None:
        seq = self.get_or_create_sequence(seq_id)
        batch = seq.get_or_create_batch(batch_public_id, tenant_public_id)
        sample = batch.get_or_create_sample(
            project_public_id, sample_public_id, file_kind
        )
        sample.mark_file_uploaded(path)

    def mark_file_failed(
        self,
        seq_id: str,
        batch_public_id: str,
        project_public_id: str,
        sample_public_id: str,
        file_kind: str,
        path: str,
        code: str,
        msg: str,
        tenant_public_id: str = "",
    ) -> None:
        seq = self.get_or_create_sequence(seq_id)
        batch = seq.get_or_create_batch(batch_public_id, tenant_public_id)
        sample = batch.get_or_create_sample(
            project_public_id, sample_public_id, file_kind
        )
        sample.mark_file_failed(path, code, msg)

    # ---- schema export ----
    def export_batch_schema_dict(self, batch_public_id: str) -> dict[str, Any]:
        """
        meta.json 용: 특정 batch 하나만 스키마로 export
        """
        return self.find_batch(batch_public_id).to_schema_dict()
