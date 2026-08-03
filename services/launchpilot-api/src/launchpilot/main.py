from fastapi import FastAPI

from launchpilot.api.routers import router as campaign_router

app = FastAPI(
    title="LaunchPilot API",
    version="0.1.0",
    description="Evidence-grounded marketing analysis portfolio rebuild",
)
app.include_router(campaign_router)


@app.get("/health", tags=["system"])
def health() -> dict[str, str]:
    return {"status": "ok"}

