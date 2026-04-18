"""
AttentionX — Health Router
GET /health  →  service liveness check
"""

from fastapi import APIRouter
from pydantic import BaseModel

router = APIRouter()


class HealthResponse(BaseModel):
    status: str
    service: str
    version: str


@router.get("/health", response_model=HealthResponse, summary="Service liveness check")
async def health_check() -> HealthResponse:
    """Returns HTTP 200 with service metadata when the API is running."""
    return HealthResponse(
        status="ok",
        service="AttentionX API",
        version="0.1.0",
    )
