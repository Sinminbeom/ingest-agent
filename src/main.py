from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from oncx_core.logger.app_logger import AppLogger

from api.routers import router as api_router
from app.ingest_agent import IngestAgent
from config.project_config import ProjectConfig
from exceptions.handler import register_exception_handlers


@asynccontextmanager
async def lifespan(app: FastAPI):
    # ======================
    # startup
    # ======================
    ProjectConfig.set_config("./conf/application.conf")
    AppLogger.set_config("./conf/logging.conf", ProjectConfig.instance().project_name)

    ingest_agent = IngestAgent()
    ingest_agent.start()
    AppLogger.instance().info("[IngestAgent] started")

    app.state.ingest_agent = ingest_agent

    yield

    # ======================
    # shutdown
    # ======================
    ingest_agent = app.state.ingest_agent
    ingest_agent.stop()
    ingest_agent.join()
    AppLogger.instance().info("[IngestAgent] stopped")


def create_app() -> FastAPI:
    app = FastAPI(
        title="Ingest Agent",
        description="Oncocross Ingest Agent",
        version="0.1.1",
        lifespan=lifespan,
        docs_url="/ingest-agent/docs",
        redoc_url="/ingest-agent/redoc",
        openapi_url="/ingest-agent/openapi.json",
    )

    register_exception_handlers(app)

    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=False,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    app.include_router(api_router)

    @app.get("/ingest-agent/health", tags=["health"])
    def health() -> dict[str, str]:
        return {"status": "ok"}

    return app


app = create_app()
