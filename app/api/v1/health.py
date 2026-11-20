"""Health check endpoints for monitoring and orchestrator probes."""

from fastapi import APIRouter, Response, status

from app.schemas.health import HealthResponse, ReadinessResponse
from app.services.health import health_service

router = APIRouter(prefix="/health", tags=["Health"])


@router.get(
    "/live",
    response_model=HealthResponse,
    summary="Process liveness probe",
    description="Returns OK if the application server process is running.",
)
def get_liveness() -> HealthResponse:
    """Return process liveness probe response."""
    return health_service.get_liveness()


@router.get(
    "/ready",
    response_model=ReadinessResponse,
    summary="Dependency readiness probe",
    description="Returns status of critical dependencies (Database, Redis).",
)
async def get_readiness(response: Response) -> ReadinessResponse:
    """Return dependency readiness probe response."""
    readiness = await health_service.get_readiness()
    if readiness.status != "ok":
        response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE
    return readiness
