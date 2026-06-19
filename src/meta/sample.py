from dataclasses import dataclass
from typing import Any, Dict, List

from utils.util import utc_now_iso


@dataclass
class Checksum:
    algo: str
    value: str


@dataclass
class FileTimestamps:
    detected_at: str | None = None
    uploaded_at: str | None = None
    verified_at: str | None = None

    def mark_detected(self) -> None:
        if self.detected_at is None:
            self.detected_at = utc_now_iso()

    def mark_uploaded(self) -> None:
        self.uploaded_at = utc_now_iso()

    def mark_verified(self) -> None:
        self.verified_at = utc_now_iso()


@dataclass
class Issue:
    code: str | None = None
    message: str | None = None
    at: str | None = None


@dataclass
class FileDiagnostics:
    warning: Issue | None = None
    error: Issue | None = None


@dataclass
class File:
    class E_FILE_STATUS:
        SUCCESS = "SUCCESS"
        FAIL = "FAIL"

    uri: str
    size_bytes: int
    checksum: Checksum
    timestamps: FileTimestamps
    status: str
    diagnostics: FileDiagnostics

    def success(self):
        self.status = self.E_FILE_STATUS.SUCCESS

    def fail(self, code: str, msg: str):
        self.status = self.E_FILE_STATUS.FAIL
        self.diagnostics.error = Issue(code, msg, utc_now_iso())


@dataclass
class Content:
    files: List[File]


@dataclass
class SampleIdentifiers:
    project_uuid: str
    sample_uuid: str
    file_kind: str


@dataclass
class Sample:
    identifiers: SampleIdentifiers
    content: Content
    extensions: Dict[str, Any]
