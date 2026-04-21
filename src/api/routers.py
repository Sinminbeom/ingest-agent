from fastapi import APIRouter

from api.v1.routers import router as v1_router

router = APIRouter()

for r in [v1_router]:
    router.include_router(r, prefix="/ingest-agent/v1")
