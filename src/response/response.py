from datetime import datetime, timezone
from typing import Generic, TypeVar, Self

from pydantic import BaseModel, Field

T = TypeVar("T")


class ApiResponse(BaseModel, Generic[T]):
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    status: int
    data: T

    @classmethod
    def ok(cls, data: T, status: int = 200) -> Self:
        return cls(status=status, data=data)
