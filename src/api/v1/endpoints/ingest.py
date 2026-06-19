from uuid import UUID

from fastapi import APIRouter, Depends, Request

from api.v1.deps.auth_deps import get_auth_context
from app.ingest_agent import IngestAgent
from domain.auth_context import AuthContext
from response.response import ApiResponse
from schemas.ingest import IngestStartResponse

router = APIRouter(prefix="/ingest", tags=["ingest"])


@router.post(
    "/batch/{batch_public_id}", summary="배치 파일 업로드 시작", status_code=202
)
def upload(
    batch_public_id: UUID,
    request: Request,
    ctx: AuthContext = Depends(get_auth_context),
) -> ApiResponse[IngestStartResponse]:
    ingest_agent: IngestAgent = request.app.state.ingest_agent
    ingest_agent.upload(
        str(ctx.tenant_public_id),
        str(batch_public_id),
        ctx.token,
    )
    return ApiResponse.ok(
        IngestStartResponse(batch_public_id=batch_public_id), status=202
    )
