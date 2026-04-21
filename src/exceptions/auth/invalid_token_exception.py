from exceptions.custom_exception import CustomException
from response.error_code import ErrorCode


class InvalidTokenException(CustomException):
    def __init__(self) -> None:
        super().__init__(ErrorCode.INVALID_TOKEN)
