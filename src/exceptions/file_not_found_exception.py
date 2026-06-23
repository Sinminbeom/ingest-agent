from dataclasses import dataclass
from typing import Any, Iterable, Mapping

from exceptions.custom_exception import CustomException
from response.error_code import ErrorCode


@dataclass
class FileNotFoundException(CustomException):
    field_errors: list[Mapping[str, Any]]

    def __init__(self, missing_paths: Iterable[str]):
        self.field_errors = [
            {
                "field": "data_file_path",
                "value": path,
                "reason": "로컬 파일을 찾을 수 없습니다.",
            }
            for path in missing_paths
        ]
        super().__init__(ErrorCode.FILE_NOT_FOUND)
