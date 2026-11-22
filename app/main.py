"""FastAPI application entry point and lifespan management."""

import logging
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.api.router import api_router
from app.core.config import get_settings
from app.core.exceptions import (
    CanonicalizationError,
    HookRelayException,
    IdempotencyFingerprintMismatchError,
    PayloadTooLargeError,
    UnsupportedMediaTypeError,
)
from app.core.logging import setup_logging
from app.db.session import check_database_connection, close_database_connection
from app.integrations.redis import redis_client

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None]:
    """Application lifespan manager handling startup and shutdown hooks."""
    settings = get_settings()
    setup_logging(settings.LOG_LEVEL)
    logger.info("Starting %s in %s environment", settings.PROJECT_NAME, settings.ENVIRONMENT)

    # In non-testing environments, verify database connection at startup
    if settings.ENVIRONMENT != "testing":
        try:
            await check_database_connection()
            logger.info("Database connectivity verified")
        except Exception as exc:
            logger.error("Startup database check failed: %s", exc)
            if settings.ENVIRONMENT == "production":
                raise

    yield

    # Clean shutdown
    logger.info("Shutting down %s", settings.PROJECT_NAME)
    await close_database_connection()
    await redis_client.close()


def create_app() -> FastAPI:
    """Application factory for HookRelay."""
    settings = get_settings()

    application = FastAPI(
        title=settings.PROJECT_NAME,
        description="High-performance webhook delivery engine",
        version="0.1.0",
        debug=settings.DEBUG,
        lifespan=lifespan,
    )

    # CORS configuration
    application.add_middleware(
        CORSMiddleware,
        allow_origins=["*"] if settings.DEBUG else [],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # Exception handlers
    @application.exception_handler(CanonicalizationError)
    async def canonicalization_exception_handler(
        request: Request,
        exc: CanonicalizationError,
    ) -> JSONResponse:
        logger.warning("Canonicalization rejection: %s (%s)", exc.error_code, exc.message)
        return JSONResponse(
            status_code=status.HTTP_400_BAD_REQUEST,
            content={"error": exc.error_code, "message": exc.message},
        )

    @application.exception_handler(IdempotencyFingerprintMismatchError)
    async def idempotency_conflict_handler(
        request: Request,
        exc: IdempotencyFingerprintMismatchError,
    ) -> JSONResponse:
        logger.warning("Idempotency fingerprint conflict: %s", exc.message)
        return JSONResponse(
            status_code=status.HTTP_409_CONFLICT,
            content={"error": exc.error_code, "message": exc.message},
        )

    @application.exception_handler(PayloadTooLargeError)
    async def payload_too_large_handler(
        request: Request,
        exc: PayloadTooLargeError,
    ) -> JSONResponse:
        logger.warning("Payload size exceeded: %s", exc.message)
        return JSONResponse(
            status_code=413,
            content={"error": exc.error_code, "message": exc.message},
        )

    @application.exception_handler(UnsupportedMediaTypeError)
    async def unsupported_media_type_handler(
        request: Request,
        exc: UnsupportedMediaTypeError,
    ) -> JSONResponse:
        logger.warning("Unsupported media type: %s", exc.message)
        return JSONResponse(
            status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
            content={"error": exc.error_code, "message": exc.message},
        )

    @application.exception_handler(HookRelayException)
    async def hookrelay_exception_handler(
        request: Request,
        exc: HookRelayException,
    ) -> JSONResponse:
        logger.error("HookRelay domain exception: %s", exc.message)
        return JSONResponse(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            content={"error": exc.__class__.__name__, "message": exc.message},
        )

    # Register API routers under /api
    application.include_router(api_router, prefix="/api")

    @application.get("/", include_in_schema=False)
    async def root_redirect() -> dict[str, str]:
        return {
            "name": settings.PROJECT_NAME,
            "version": "0.1.0",
            "docs_url": "/docs",
            "health_url": "/api/v1/health/live",
        }

    return application


app = create_app()
