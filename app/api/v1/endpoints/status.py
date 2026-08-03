from fastapi import APIRouter, Request

router = APIRouter(tags=["status"])


@router.get("/status")
async def info(request: Request) -> dict[str, object]:
    """Return request metadata for debugging and diagnostics."""
    return {
        "python_version": "test_version",
	"uptime": "test_uptime",
	"app_version": "test_app_version",
    }
