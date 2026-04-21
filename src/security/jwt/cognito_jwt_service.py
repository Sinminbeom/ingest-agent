import json
from uuid import UUID

import httpx
from jose import ExpiredSignatureError, JWTError, jwt

from config.project_config import ProjectConfig
from exceptions.auth.expired_token_exception import ExpiredTokenException
from exceptions.auth.invalid_token_exception import InvalidTokenException
from schemas.auth.jwt_claims_request import JwtClaimsRequest
from security.jwt.jwt_service import IJwtService


class CognitoJwtService(IJwtService):
    def __init__(self) -> None:
        config = ProjectConfig.instance()
        self._jwks_url = (
            f"https://cognito-idp.{config.region_name}.amazonaws.com"
            f"/{config.cognito_user_pool_id}/.well-known/jwks.json"
        )
        self._jwks: dict | None = None

    def _get_jwks(self) -> dict:
        if self._jwks is None:
            resp = httpx.get(self._jwks_url, timeout=5.0)
            resp.raise_for_status()
            self._jwks = resp.json()
        return self._jwks  # type: ignore[return-value]

    def verify_access(self, token: str) -> JwtClaimsRequest:
        try:
            payload = jwt.decode(
                token,
                self._get_jwks(),
                algorithms=["RS256"],
                options={"verify_aud": False},
            )
        except ExpiredSignatureError as e:
            raise ExpiredTokenException() from e
        except JWTError as e:
            raise InvalidTokenException() from e

        return self._to_claims(payload)

    @staticmethod
    def _to_claims(payload: dict) -> JwtClaimsRequest:
        try:
            member_public_id = UUID(payload["custom:member_id"])
            roles_raw = payload.get("custom:roles", "[]")
            roles = tuple(
                json.loads(roles_raw) if isinstance(roles_raw, str) else roles_raw
            )
        except Exception as e:
            raise InvalidTokenException() from e

        return JwtClaimsRequest(
            member_public_id=member_public_id,
            roles=roles,
        )
