from uuid import UUID

from pydantic import BaseModel


class IngestStartResponse(BaseModel):
    batch_public_id: UUID
    status: str = "ACCEPTED"
