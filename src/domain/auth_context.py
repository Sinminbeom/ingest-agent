from dataclasses import dataclass
from uuid import UUID

from schemas.auth.jwt_claims_request import JwtClaimsRequest


@dataclass(slots=True, frozen=True)
class AuthContext:
    token: str
    claims: JwtClaimsRequest
    tenant_public_id: UUID
