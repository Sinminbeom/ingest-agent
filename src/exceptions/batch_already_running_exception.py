from exceptions.custom_exception import CustomException
from response.error_code import ErrorCode


class BatchAlreadyRunningException(CustomException):
    def __init__(self) -> None:
        super().__init__(ErrorCode.BATCH_ALREADY_RUNNING)
