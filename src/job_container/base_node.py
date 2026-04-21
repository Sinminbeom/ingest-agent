class BaseNode:
    """
    Composite 패턴의 공통 인터페이스.
    Leaf(JobContainer / SampleContainer)와 Composite(나머지 컨테이너)가 모두 이걸 상속.
    """

    def is_all_completed(self) -> bool:
        raise NotImplementedError

    def clear_all(self) -> None:
        raise NotImplementedError

    def to_dict(self) -> dict:
        raise NotImplementedError
