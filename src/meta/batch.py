from dataclasses import dataclass
from typing import Dict, Any

from utils.util import utc_now_iso


@dataclass
class BatchIdentifiers:
    tenant_uuid: str
    batch_uuid: str


@dataclass
class Acquisition:
    software: Dict[str, str]
    mode: Dict[str, str]


@dataclass
class Source:
    type: str
    name: str
    version: str


@dataclass
class BatchContent:
    source: Source
    acquisition: Acquisition


@dataclass
class Timestamps:
    requested_at: str | None = None
    ingested_at: str | None = None

    def mark_requested(self) -> None:
        if self.requested_at is None:
            self.requested_at = utc_now_iso()

    def mark_ingested(self) -> None:
        self.ingested_at = utc_now_iso()


@dataclass
class Diagnostics:
    warnings: list
    errors: list


@dataclass
class Batch:
    identifiers: BatchIdentifiers
    content: BatchContent
    timestamps: Timestamps
    status: str
    diagnostics: Diagnostics
    extensions: Dict[str, Any]
