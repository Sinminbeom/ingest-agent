from dataclasses import dataclass

from response.error_code import ErrorCode


@dataclass
class CustomException(RuntimeError):
    error_code: ErrorCode

    def __post_init__(self) -> None:
        super().__init__(self.error_code.message)
