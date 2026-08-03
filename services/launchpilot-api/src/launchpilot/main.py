from fastapi import FastAPI

from launchpilot.api.routers import router as campaign_router
from launchpilot.api.auth import router as auth_router
from launchpilot.api.connections import router as connection_router

app = FastAPI(
    title="LaunchPilot API",
    version="0.1.0",
    description="Evidence-grounded marketing analysis portfolio rebuild",
)
app.include_router(campaign_router)
app.include_router(auth_router)
app.include_router(connection_router)


@app.get("/health", tags=["system"])
def health() -> dict[str, str]:
    return {"status": "ok"}
