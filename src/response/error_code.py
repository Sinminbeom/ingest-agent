from enum import Enum


class ErrorCode(Enum):
    INVALID_PARAMETER = (400, "I000", "유효하지 않은 데이터입니다")
    INVALID_TOKEN = (401, "A001", "유효하지 않은 인증 토큰입니다.")
    EXPIRED_TOKEN = (401, "A002", "인증 토큰이 만료되었습니다.")
    NOT_FOUND = (404, "R001", "리소스를 찾을 수 없습니다.")
    FILE_NOT_FOUND = (404, "F001", "업로드할 파일을 찾을 수 없습니다.")

    def __init__(self, status: int, code: str, message: str) -> None:
        self.status: int = status
        self.code: str = code
        self.message: str = message
