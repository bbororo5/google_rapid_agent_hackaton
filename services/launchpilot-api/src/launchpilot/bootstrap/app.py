from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI

from launchpilot.api.ads_connections import router as ads_connection_router
from launchpilot.api.auth import router as auth_router
from launchpilot.api.campaign_analysis import router as campaign_analysis_router
from launchpilot.api.connections import router as connection_router
from launchpilot.api.workspaces import router as workspace_router
from launchpilot.bootstrap.config import Settings
from launchpilot.campaigns.api import router as campaign_router
from launchpilot.campaigns.bindings_api import router as campaign_binding_router
from launchpilot.knowledge.api import router as campaign_document_router
from launchpilot.observability.runtime import TelemetryRuntime
from launchpilot.performance.api import router as observation_router

telemetry = TelemetryRuntime(Settings.from_environment())


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    try:
        yield
    finally:
        telemetry.shutdown()


app = FastAPI(
    title="LaunchPilot API",
    version="0.1.0",
    description="Evidence-grounded marketing analysis portfolio rebuild",
    lifespan=lifespan,
)
telemetry.start(app)
app.include_router(campaign_router)
app.include_router(campaign_analysis_router)
app.include_router(campaign_binding_router)
app.include_router(campaign_document_router)
app.include_router(observation_router)
app.include_router(auth_router)
app.include_router(connection_router)
app.include_router(ads_connection_router)
app.include_router(workspace_router)


@app.get("/health", tags=["system"])
def health() -> dict[str, str]:
    return {"status": "ok"}
