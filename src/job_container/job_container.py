from typing import Iterable, Set

from job_container.base_node import BaseNode


class JobContainer(BaseNode):
    """
    Leaf 역할 — 샘플 하나에 대응하는 실제 Job 상태 저장.
    - marker_container   : 아직 완료 안 된 작업 마커
    - complete_container : 완료된 작업 마커
    """

    def __init__(self) -> None:
        self.marker_container: Set[str] = set()
        self.complete_container: Set[str] = set()

    # -------- 마커 추가 --------
    def add_marker(self, marker: str) -> None:
        self.marker_container.add(marker)

    def add_markers(self, markers: Iterable[str]) -> None:
        self.marker_container.update(markers)

    # -------- 완료 처리 --------
    def mark_complete(self, marker: str) -> None:
        if marker in self.marker_container:
            self.marker_container.remove(marker)
            self.complete_container.add(marker)

    def is_marker_done(self, marker: str) -> bool:
        return marker in self.complete_container

    # -------- BaseNode 구현 --------
    def is_all_completed(self) -> bool:
        return len(self.marker_container) == 0

    def clear_all(self) -> None:
        self.marker_container.clear()
        self.complete_container.clear()

    def to_dict(self) -> dict:
        """
        스키마의 job 개념은 별도 정의되어 있지 않으므로 내부 상태 표현(디버깅/상태 저장용) 유지.
        """
        return {
            "markers": sorted(self.marker_container),
            "completed": sorted(self.complete_container),
        }

    def __repr__(self) -> str:
        return f"JobContainer(markers={len(self.marker_container)}, completed={len(self.complete_container)})"
