"""Pytest configuration and shared fixtures for HookRelay."""

import os
from collections.abc import AsyncGenerator

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy import make_url, text
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

# Enforce testing environment
os.environ["ENVIRONMENT"] = "testing"
os.environ["DEBUG"] = "true"

from app.core.config import get_settings
from app.db.base import Base
from app.db.session import get_db_session
from app.main import create_app


def validate_test_database_target(db_url: str) -> None:
    """Safeguard: Prevent destructive operations on non-test databases."""
    parsed = make_url(db_url)
    database_name = (parsed.database or "").lower()
    if not database_name:
        raise ValueError("Test database name cannot be empty")
    if "test" not in database_name:
        raise ValueError(
            f"SAFETY VIOLATION: Database '{database_name}' does not contain 'test'. "
            "Destructive test operations are prohibited on non-test databases."
        )


def get_verified_test_database_url() -> str:
    """Retrieve and strictly validate the test database URL from environment configuration."""
    test_url = os.environ.get("TEST_DATABASE_URL")
    if not test_url:
        settings = get_settings()
        if settings.TEST_DATABASE_URL:
            test_url = str(settings.TEST_DATABASE_URL)
        else:
            test_url = str(settings.DATABASE_URL)

    validate_test_database_target(test_url)
    return test_url


@pytest.fixture
def test_db_url() -> str:
    """Provide verified test database URL."""
    return get_verified_test_database_url()


@pytest_asyncio.fixture
async def test_engine(test_db_url: str) -> AsyncGenerator[AsyncEngine]:
    """Create test database engine connecting to real PostgreSQL."""
    engine = create_async_engine(test_db_url, echo=False)

    # Ensure clean slate before test
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    yield engine

    # Ensure clean slate after test
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
        await conn.execute(text("DROP TABLE IF EXISTS _m0_baseline_marker CASCADE;"))
        await conn.execute(text("DROP TABLE IF EXISTS alembic_version CASCADE;"))

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
