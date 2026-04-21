from typing import Dict, Optional, Iterable, Tuple

from job_container.base_node import BaseNode


class CompositeNode(BaseNode):
    """
    자식 노드를 가질 수 있는 공통 Composite 구현.
    - name: 이 노드의 식별자 (batch_id, experiment_id, sample_id 등)
    - _children: key -> BaseNode
    """

    def __init__(self, name: str) -> None:
        self.name: str = name
        self._children: Dict[str, BaseNode] = dict()

    # -------- 자식 관리 --------
    def add_child(self, key: str, child: BaseNode) -> None:
        self._children[key] = child

    def get_child(self, key: str) -> Optional[BaseNode]:
        return self._children.get(key)

    def iter_children(self) -> Iterable[Tuple[str, BaseNode]]:
        return self._children.items()

    # -------- 완료/초기화 공통 구현 --------
    def is_all_completed(self) -> bool:
        if not self._children:
            return True
        return all(child.is_all_completed() for _, child in self._children.items())

    def clear_all(self) -> None:
        for _, child in self._children.items():
            child.clear_all()
        self._children.clear()

    # -------- 디버깅용 --------
    def to_dict(self) -> dict:
        return {
            "name": self.name,
            "children": {k: v.to_dict() for k, v in self._children.items()},
        }

    def __repr__(self) -> str:
        return f"{self.__class__.__name__}(name={self.name!r}, children={len(self._children)})"
