"""Unit tests for health endpoints and service."""

import pytest
from httpx import AsyncClient

from app.services.health import health_service


@pytest.mark.asyncio
async def test_liveness_endpoint(async_client: AsyncClient) -> None:
    """Verify GET /api/v1/health/live returns HTTP 200 with ok status."""
    response = await async_client.get("/api/v1/health/live")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "ok"
    assert "environment" in data
    assert data["version"] == "0.1.0"


@pytest.mark.asyncio
async def test_root_endpoint(async_client: AsyncClient) -> None:
    """Verify root info endpoint."""
    response = await async_client.get("/")
    assert response.status_code == 200
    data = response.json()
    assert data["name"] == "HookRelay"
    assert data["docs_url"] == "/docs"


@pytest.mark.asyncio
async def test_readiness_endpoint(async_client: AsyncClient) -> None:
    """Verify GET /api/v1/health/ready reports dependency statuses."""
    response = await async_client.get("/api/v1/health/ready")
    assert response.status_code in (200, 503)
    data = response.json()
    assert "status" in data
    assert "database" in data
    assert "redis" in data
    assert data["version"] == "0.1.0"


def test_health_service_liveness() -> None:
    """Test health service liveness method directly."""
    res = health_service.get_liveness()
    assert res.status == "ok"
    assert res.version == "0.1.0"
