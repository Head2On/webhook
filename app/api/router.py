"""Top-level API router registering versioned routers."""

from fastapi import APIRouter

from app.api.v1.health import router as health_router
from app.api.v1.webhooks import router as webhooks_router

api_router = APIRouter()

# Include version 1 routers
api_router.include_router(health_router, prefix="/v1")
api_router.include_router(webhooks_router, prefix="/v1")
