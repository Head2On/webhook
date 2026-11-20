"""SQLAlchemy 2.x database session and engine lifecycle management."""

import logging
from collections.abc import AsyncGenerator

from sqlalchemy import text
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from app.core.config import get_settings
from app.core.exceptions import DatabaseConnectionError

logger = logging.getLogger(__name__)

settings = get_settings()

engine: AsyncEngine = create_async_engine(
    str(settings.DATABASE_URL),
    pool_size=settings.DATABASE_POOL_SIZE,
    max_overflow=settings.DATABASE_MAX_OVERFLOW,
    pool_timeout=settings.DATABASE_POOL_TIMEOUT,
    echo=settings.DEBUG,
    future=True,
)

async_session_factory: async_sessionmaker[AsyncSession] = async_sessionmaker(
    bind=engine,
    class_=AsyncSession,
    expire_on_commit=False,
    autoflush=False,
)


async def get_db_session() -> AsyncGenerator[AsyncSession]:
    """Dependency for providing a transactional database session.

    Commits on successful completion, rolls back on exception,
    and guarantees session closure.
    """
    async with async_session_factory() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise


async def check_database_connection(timeout: float = 3.0) -> bool:
    """Verify active database connectivity with a lightweight query."""
    try:
        async with engine.connect() as conn:
            result = await conn.execute(text("SELECT 1"))
            return result.scalar() == 1
    except Exception as exc:
        logger.error("Database health check failed: %s", exc)
        raise DatabaseConnectionError(f"Database check failed: {exc}") from exc


async def close_database_connection() -> None:
    """Dispose of engine connection pool on application shutdown."""
    logger.info("Disposing database engine connection pool")
    await engine.dispose()
