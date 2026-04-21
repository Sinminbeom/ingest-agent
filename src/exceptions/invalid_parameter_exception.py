from dataclasses import dataclass
from typing import Any, Iterable, Mapping

from exceptions.custom_exception import CustomException
from response.error_code import ErrorCode


@dataclass
class InvalidParameterException(CustomException):
    field_errors: list[Mapping[str, Any]]

    def __init__(self, field_errors: Iterable[Mapping[str, Any]]):
        self.field_errors = list(field_errors)
        super().__init__(ErrorCode.INVALID_PARAMETER)
