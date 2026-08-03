"""Info endpoint — returns request metadata."""

from fastapi import APIRouter, Request

router = APIRouter(tags=["info"])


@router.get("/info")
async def info(request: Request) -> dict[str, object]:
    """Return request metadata for debugging and diagnostics."""
    return {
        "host": request.client.host if request.client else None,
        "headers": dict(request.headers),
        "method": request.method,
        "url": str(request.url),
    }