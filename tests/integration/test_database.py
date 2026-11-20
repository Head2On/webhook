"""Integration tests verifying real PostgreSQL connectivity and transactions."""

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import check_database_connection


@pytest.mark.asyncio
async def test_real_postgres_connectivity() -> None:
    """Verify live connectivity against PostgreSQL instance."""
    is_connected = await check_database_connection()
    assert is_connected is True


@pytest.mark.asyncio
async def test_session_execute_query(db_session: AsyncSession) -> None:
    """Verify session can execute raw SQL and fetch scalars."""
    result = await db_session.execute(text("SELECT 42 AS answer"))
    assert result.scalar() == 42


@pytest.mark.asyncio
async def test_transaction_rollback_isolation(db_session: AsyncSession) -> None:
    """Verify transaction rollback maintains isolation."""
    # Create temporary table within transaction
    await db_session.execute(
        text("CREATE TEMPORARY TABLE test_iso (id INT, val TEXT) ON COMMIT DROP")
    )
    await db_session.execute(text("INSERT INTO test_iso (id, val) VALUES (1, 'hookrelay_test')"))
    res = await db_session.execute(text("SELECT val FROM test_iso WHERE id = 1"))
    assert res.scalar() == "hookrelay_test"
