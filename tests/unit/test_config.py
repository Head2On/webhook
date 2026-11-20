"""Unit tests for configuration loading and validation."""

import pytest
from pydantic import ValidationError

from app.core.config import Settings


def test_settings_default_values() -> None:
    """Test default settings attributes."""
    settings = Settings(
        DATABASE_URL="postgresql+asyncpg://postgres:secret@localhost:5432/hookrelay",
    )
    assert settings.PROJECT_NAME == "HookRelay"
    assert settings.API_V1_PREFIX == "/api/v1"
    assert settings.DATABASE_POOL_SIZE == 10
    assert settings.REDIS_URL == "redis://localhost:6379/0"


def test_invalid_database_url_scheme() -> None:
    """Verify rejection of non-async database URL scheme."""
    with pytest.raises(ValidationError) as exc_info:
        Settings(DATABASE_URL="sqlite:///test.db")
    assert "DATABASE_URL" in str(exc_info.value)


def test_production_debug_not_allowed() -> None:
    """Verify that debug mode is forbidden in production environment."""
    with pytest.raises(ValidationError) as exc_info:
        Settings(
            ENVIRONMENT="production",
            DEBUG=True,
            DATABASE_URL="postgresql+asyncpg://user:pass@db.prod.internal:5432/hookrelay",
        )
    assert "DEBUG mode must be disabled in production" in str(exc_info.value)


def test_production_localhost_database_not_allowed() -> None:
    """Verify that localhost database is forbidden in production environment."""
    with pytest.raises(ValidationError) as exc_info:
        Settings(
            ENVIRONMENT="production",
            DEBUG=False,
            DATABASE_URL="postgresql+asyncpg://user:pass@localhost:5432/hookrelay",
        )
    assert "DATABASE_URL cannot point to localhost in production" in str(exc_info.value)


def test_sync_database_url_conversion() -> None:
    """Verify conversion of asyncpg URL to sync URL for tooling."""
    settings = Settings(
        DATABASE_URL="postgresql+asyncpg://postgres:pass@localhost:5432/hookrelay",
    )
    assert settings.sync_database_url == "postgresql://postgres:pass@localhost:5432/hookrelay"


def test_test_database_target_safety_check() -> None:
    """Verify that targeting a non-test database raises a safety violation."""
    from tests.conftest import validate_test_database_target

    # Must raise when target database lacks 'test'
    with pytest.raises(ValueError, match="SAFETY VIOLATION"):
        validate_test_database_target("postgresql+asyncpg://postgres:pass@localhost:5432/hookrelay")

    with pytest.raises(ValueError, match="SAFETY VIOLATION"):
        validate_test_database_target(
            "postgresql+asyncpg://postgres:pass@localhost:5432/production_db"
        )

    # Must pass when database contains 'test'
    validate_test_database_target(
        "postgresql+asyncpg://postgres:pass@localhost:5432/hookrelay_test"
    )
    validate_test_database_target("postgresql+asyncpg://postgres:pass@localhost:5432/my_test_db_2")
