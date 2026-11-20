"""Integration tests for Alembic schema migrations against PostgreSQL."""

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine

from app.core.config import get_settings


@pytest.mark.asyncio
async def test_alembic_migrations_lifecycle(test_engine: AsyncEngine) -> None:
    """Test full migration lifecycle: upgrade to head, verify table, downgrade."""
    settings = get_settings()
    db_url = str(settings.TEST_DATABASE_URL or settings.DATABASE_URL)

    alembic_cfg = Config("alembic.ini")
    alembic_cfg.set_main_option("sqlalchemy.url", db_url)

    # Apply all migrations to head
    command.upgrade(alembic_cfg, "head")

    # Verify marker table exists
    async with test_engine.connect() as conn:
        result = await conn.execute(
            text(
                "SELECT EXISTS ("
                "  SELECT FROM information_schema.tables "
                "  WHERE table_name = '_m0_baseline_marker'"
                ");"
            )
        )
        assert result.scalar() is True

    # Downgrade back to base
    command.downgrade(alembic_cfg, "base")

    # Verify marker table was dropped
    async with test_engine.connect() as conn:
        result = await conn.execute(
            text(
                "SELECT EXISTS ("
                "  SELECT FROM information_schema.tables "
                "  WHERE table_name = '_m0_baseline_marker'"
                ");"
            )
        )
        assert result.scalar() is False

    # Re-apply upgrade to leave database clean for subsequent operations
    command.upgrade(alembic_cfg, "head")
