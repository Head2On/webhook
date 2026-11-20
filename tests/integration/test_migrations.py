"""Integration tests for Alembic schema migrations against PostgreSQL."""

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine

from tests.conftest import get_verified_test_database_url


@pytest.mark.asyncio
async def test_alembic_migrations_lifecycle(test_engine: AsyncEngine) -> None:
    """Test full migration lifecycle: upgrade to head, verify table, downgrade to base."""
    db_url = get_verified_test_database_url()

    alembic_cfg = Config("alembic.ini")
    alembic_cfg.set_main_option("sqlalchemy.url", db_url)

    try:
        # 1. Apply all migrations to head
        command.upgrade(alembic_cfg, "head")

        # 2. Verify marker table exists
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

        # 3. Downgrade back to base
        command.downgrade(alembic_cfg, "base")

        # 4. Verify marker table was dropped
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
    finally:
        # Ensure complete cleanup of any migration/alembic state
        async with test_engine.begin() as conn:
            await conn.execute(text("DROP TABLE IF EXISTS _m0_baseline_marker CASCADE;"))
            await conn.execute(text("DROP TABLE IF EXISTS alembic_version CASCADE;"))
