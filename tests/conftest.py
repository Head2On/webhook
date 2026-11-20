"""Pytest configuration and shared fixtures for HookRelay."""

import os
from collections.abc import AsyncGenerator

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

# Enforce testing environment before settings are initialized
os.environ["ENVIRONMENT"] = "testing"
os.environ["DEBUG"] = "true"
if not os.environ.get("TEST_DATABASE_URL") and not os.environ.get("DATABASE_URL"):
    os.environ["DATABASE_URL"] = "postgresql+asyncpg://postgres:8520@localhost:5432/hookrelay_test"

from app.core.config import get_settings
from app.db.base import Base
from app.db.session import get_db_session
from app.main import create_app


@pytest.fixture
def test_settings():
    """Provide application settings configured for test environment."""
    return get_settings()


@pytest_asyncio.fixture
async def test_engine(test_settings) -> AsyncGenerator[AsyncEngine]:
    """Create test database engine connecting to real PostgreSQL."""
    db_url = str(test_settings.TEST_DATABASE_URL or test_settings.DATABASE_URL)
    engine = create_async_engine(db_url, echo=False)

    # Prepare schema in test database
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    yield engine

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)

    await engine.dispose()


@pytest_asyncio.fixture
async def db_session(test_engine: AsyncEngine) -> AsyncGenerator[AsyncSession]:
    """Provide isolated transactional database session rolled back after test."""
    session_maker = async_sessionmaker(
        bind=test_engine,
        class_=AsyncSession,
        expire_on_commit=False,
    )
    async with session_maker() as session:
        yield session
        await session.rollback()


@pytest_asyncio.fixture
async def async_client(test_engine: AsyncEngine) -> AsyncGenerator[AsyncClient]:
    """Provide HTTPX AsyncClient wired to test app with DB session override."""
    app = create_app()

    async def override_get_db_session() -> AsyncGenerator[AsyncSession]:
        session_maker = async_sessionmaker(
            bind=test_engine,
            class_=AsyncSession,
            expire_on_commit=False,
        )
        async with session_maker() as session:
            yield session

    app.dependency_overrides[get_db_session] = override_get_db_session

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        yield client
