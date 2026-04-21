from uuid import UUID

from fastapi import Depends, Header
from fastapi.security import OAuth2PasswordBearer

from domain.auth_context import AuthContext
from schemas.auth.jwt_claims_request import JwtClaimsRequest
from security.jwt.cognito_jwt_service import CognitoJwtService
from security.jwt.jwt_service import IJwtService

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/account-server/v1/auth/login")


def get_jwt_service() -> IJwtService:
    return CognitoJwtService()


def get_auth_context(
    token: str = Depends(oauth2_scheme),
    x_tenant_id: UUID = Header(..., alias="X-Tenant-Id"),
    jwt_service: IJwtService = Depends(get_jwt_service),
) -> AuthContext:
    claims = jwt_service.verify_access(token)
    return AuthContext(token=token, claims=claims, tenant_public_id=x_tenant_id)
