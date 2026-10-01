from exceptions.custom_exception import CustomException
from response.error_code import ErrorCode


class ProjectAccessDeniedException(CustomException):
    def __init__(self) -> None:
        super().__init__(ErrorCode.PROJECT_ACCESS_DENIED)
