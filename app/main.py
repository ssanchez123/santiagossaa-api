"""Santiago API — Main application entrypoint."""

from datetime import datetime, timezone

from fastapi import FastAPI

from app.api.v1.endpoints import health, info
from app.core.config import get_settings

settings = get_settings()

app = FastAPI(
    title=settings.app_name,
    description=settings.app_description,
    version=settings.app_version,
)

# Register v1 endpoints
app.include_router(health.router, prefix="/api/v1")
app.include_router(info.router, prefix="/api/v1")

# Also expose health at root level for Docker healthcheck
app.include_router(health.router)


@app.get("/")
async def root() -> dict[str, str]:
    """Root endpoint — basic server info."""
    return {
        "status": "ok",
        "message": "Hello from m1cr0l1n0",
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "server": "m1cr0l1n0",
        "version": settings.app_version,
        "deploy": "git-push-to-deploy with AI review",
    }