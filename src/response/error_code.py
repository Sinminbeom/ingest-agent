from enum import Enum


class ErrorCode(Enum):
    INVALID_PARAMETER = (400, "I000", "유효하지 않은 데이터입니다")
    INVALID_TOKEN = (401, "A001", "유효하지 않은 인증 토큰입니다.")
    EXPIRED_TOKEN = (401, "A002", "인증 토큰이 만료되었습니다.")
    PROJECT_ACCESS_DENIED = (
        403,
        "P001",
        "접근 권한이 없는 프로젝트의 파일이 있어 업로드할 수 없습니다. 프로젝트 권한을 확인해 주세요.",
    )
    NOT_FOUND = (404, "R001", "리소스를 찾을 수 없습니다.")
    BATCH_ALREADY_RUNNING = (409, "B001", "이미 업로드가 진행 중인 배치입니다.")
    FILE_NOT_FOUND = (404, "F001", "업로드할 파일을 찾을 수 없습니다.")

    def __init__(self, status: int, code: str, message: str) -> None:
        self.status: int = status
        self.code: str = code
        self.message: str = message
