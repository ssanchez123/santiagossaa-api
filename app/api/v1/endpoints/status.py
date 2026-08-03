
router = APIRouter(tags=["status"])


@router.get("/info")
async def info(request: Request) -> dict[str, object]:
    """Return request metadata for debugging and diagnostics."""
    return {
        "python_version": "test_version",
	"uptime": "test_uptime",
	"app_version": "test_app_version",
    }
