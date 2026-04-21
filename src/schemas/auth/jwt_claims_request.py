from dataclasses import dataclass
from uuid import UUID


@dataclass(frozen=True)
class JwtClaimsRequest:
    member_public_id: UUID
    roles: tuple[str, ...] = ()
