from typing import Iterable, Set


class JobContainer:
    """
    배치 하나의 파일별 완료 여부.
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

    def is_all_completed(self) -> bool:
        return len(self.marker_container) == 0

    def __repr__(self) -> str:
        return f"JobContainer(markers={len(self.marker_container)}, completed={len(self.complete_container)})"
