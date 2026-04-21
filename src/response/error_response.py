from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Iterable, List, Mapping, Self

from response.error_code import ErrorCode


@dataclass(frozen=True)
class CustomFieldError:
    field: str
    value: Any
    reason: str


@dataclass
class ErrorResponse:
    timestamp: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    status: int | None = None
    code: str | None = None
    message: str | None = None
    errors: List[CustomFieldError] | None = None

    @classmethod
    def create(cls) -> Self:
        return cls()

    def with_status(self, status: int) -> Self:
        self.status = status
        return self

    def with_message(self, message: str) -> Self:
        self.message = message
        return self

    def with_error_code(self, error_code: ErrorCode) -> Self:
        self.status = error_code.status
        self.code = error_code.code
        self.message = error_code.message
        return self

    def with_field_errors(self, field_errors: Iterable[Mapping[str, Any]]) -> Self:
        self.errors = [
            CustomFieldError(
                field=str(e.get("field", "")),
                value=e.get("value"),
                reason=str(e.get("reason", "")),
            )
            for e in field_errors
        ]
        return self

    def to_dict(self) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "timestamp": self.timestamp.isoformat(),
            "status": self.status,
            "code": self.code,
            "message": self.message,
        }
        if self.errors is not None:
            payload["errors"] = [
                {"field": e.field, "value": e.value, "reason": e.reason}
                for e in self.errors
            ]
        return payload
