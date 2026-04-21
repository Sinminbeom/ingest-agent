from fastapi import APIRouter

from api.v1.endpoints.ingest import router as ingest_router

router = APIRouter()

for r in [
    ingest_router,
]:
    router.include_router(r)
