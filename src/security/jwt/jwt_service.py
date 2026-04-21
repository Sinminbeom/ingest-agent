from abc import ABC, abstractmethod

from schemas.auth.jwt_claims_request import JwtClaimsRequest


class IJwtService(ABC):
    @abstractmethod
    def verify_access(self, token: str) -> JwtClaimsRequest:
        raise NotImplementedError
