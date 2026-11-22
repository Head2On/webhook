"""Integration tests for payload retention and physical cleanup (M1 Gate 3)."""

import uuid
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.idempotency import Delivery, Event, IdempotencyKey, Outbox
from app.services.retention import retention_service


def test_calculate_cleanup_cutoff_validation() -> None:
    """Verify retention calculation and range validation (1-60 days)."""
    now = datetime(2026, 11, 22, 12, 0, 0, tzinfo=UTC)

    # 1. Default (7 days retention + 7 days grace = 14 days)
    cutoff_default = retention_service.calculate_cleanup_cutoff(as_of=now)
    assert cutoff_default == now - timedelta(days=14)

    # 2. Min boundary (1 day retention + 7 days grace = 8 days)
    cutoff_min = retention_service.calculate_cleanup_cutoff(retention_days=1, as_of=now)
    assert cutoff_min == now - timedelta(days=8)

    # 3. Max boundary (60 days retention + 7 days grace = 67 days)
    cutoff_max = retention_service.calculate_cleanup_cutoff(retention_days=60, as_of=now)
    assert cutoff_max == now - timedelta(days=67)

    # 4. Out of bounds: 0 days
    with pytest.raises(ValueError, match="between 1 and 60 days"):
        retention_service.calculate_cleanup_cutoff(retention_days=0, as_of=now)

    # 5. Out of bounds: 61 days
    with pytest.raises(ValueError, match="between 1 and 60 days"):
        retention_service.calculate_cleanup_cutoff(retention_days=61, as_of=now)


@pytest.mark.asyncio
async def test_purge_expired_records_respects_grace_period(
    db_session: AsyncSession,
) -> None:
    """Verify physical cleanup removes records older than retention + grace period.

    Records within retention or within the 7-day grace period are preserved.
    """
    now = datetime.now(UTC)
    project_id = uuid.uuid4()

    # 1. Event A: 20 days old (exceeds 7 days retention + 7 days grace = 14 days) -> MUST BE PURGED
    key_a = IdempotencyKey(
        id=uuid.uuid4(),
        project_id=project_id,
        idempotency_key="key_a_20_days_old",
        fingerprint="jcs-rfc8785-v1:" + "1" * 64,
        created_at=now - timedelta(days=20),
        expires_at=now - timedelta(days=13),
        retired_at=now - timedelta(days=15),
    )
    db_session.add(key_a)
    await db_session.flush()

    event_a = Event(
        id=uuid.uuid4(),
        project_id=project_id,
        idempotency_key_id=key_a.id,
        event_type="old.event.a",
        raw_payload_bytes=b'{"a": 20}',
        payload_hash=key_a.fingerprint,
        created_at=key_a.created_at,
    )
    db_session.add(event_a)
    key_a.event_id = event_a.id
    await db_session.flush()

    outbox_a = Outbox(
        id=uuid.uuid4(),
        event_id=event_a.id,
        status="dispatched",
        created_at=key_a.created_at,
    )
    db_session.add(outbox_a)

    delivery_a = Delivery(
        id=uuid.uuid4(),
        project_id=project_id,
        event_id=event_a.id,
        status="delivered",
        created_at=key_a.created_at,
    )
    db_session.add(delivery_a)

    # 2. Event B: 10 days old (past 7d retention, within 7d grace) -> PRESERVED
    key_b = IdempotencyKey(
        id=uuid.uuid4(),
        project_id=project_id,
        idempotency_key="key_b_10_days_old",
        fingerprint="jcs-rfc8785-v1:" + "2" * 64,
        created_at=now - timedelta(days=10),
        expires_at=now - timedelta(days=3),
        retired_at=None,
    )
    db_session.add(key_b)
    await db_session.flush()

    event_b = Event(
        id=uuid.uuid4(),
        project_id=project_id,
        idempotency_key_id=key_b.id,
        event_type="grace.event.b",
        raw_payload_bytes=b'{"b": 10}',
        payload_hash=key_b.fingerprint,
        created_at=key_b.created_at,
    )
    db_session.add(event_b)
    key_b.event_id = event_b.id
    await db_session.flush()

    outbox_b = Outbox(
        id=uuid.uuid4(),
        event_id=event_b.id,
        status="pending",
        created_at=key_b.created_at,
    )
    db_session.add(outbox_b)

    delivery_b = Delivery(
        id=uuid.uuid4(),
        project_id=project_id,
        event_id=event_b.id,
        status="pending",
        created_at=key_b.created_at,
    )
    db_session.add(delivery_b)

    # 3. Event C: 2 days old (active, well within retention) -> MUST BE PRESERVED
    key_c = IdempotencyKey(
        id=uuid.uuid4(),
        project_id=project_id,
        idempotency_key="key_c_2_days_old",
        fingerprint="jcs-rfc8785-v1:" + "3" * 64,
        created_at=now - timedelta(days=2),
        expires_at=now + timedelta(days=5),
        retired_at=None,
    )
    db_session.add(key_c)
    await db_session.flush()

    event_c = Event(
        id=uuid.uuid4(),
        project_id=project_id,
        idempotency_key_id=key_c.id,
        event_type="active.event.c",
        raw_payload_bytes=b'{"c": 2}',
        payload_hash=key_c.fingerprint,
        created_at=key_c.created_at,
    )
    db_session.add(event_c)
    key_c.event_id = event_c.id
    await db_session.commit()

    # 4. Execute physical purge (retention_days=7, grace_period_days=7 -> cutoff = 14 days ago)
    res = await retention_service.purge_expired_records(
        session=db_session,
        retention_days=7,
        as_of=now,
    )

    assert res["purged_events"] == 1
    assert res["purged_deliveries"] == 1
    assert res["purged_outbox"] == 1
    assert res["purged_keys"] == 1

    # 5. Verify database state
    # Event A and its children are deleted
    assert (
        await db_session.execute(select(Event).where(Event.id == event_a.id))
    ).scalar_one_or_none() is None
    assert (
        await db_session.execute(select(Outbox).where(Outbox.id == outbox_a.id))
    ).scalar_one_or_none() is None
    assert (
        await db_session.execute(select(Delivery).where(Delivery.id == delivery_a.id))
    ).scalar_one_or_none() is None
    assert (
        await db_session.execute(select(IdempotencyKey).where(IdempotencyKey.id == key_a.id))
    ).scalar_one_or_none() is None

    # Event B (in grace period) is intact
    assert (
        await db_session.execute(select(Event).where(Event.id == event_b.id))
    ).scalar_one_or_none() is not None
    assert (
        await db_session.execute(select(Outbox).where(Outbox.id == outbox_b.id))
    ).scalar_one_or_none() is not None
    assert (
        await db_session.execute(select(Delivery).where(Delivery.id == delivery_b.id))
    ).scalar_one_or_none() is not None

    # Event C (active) is intact
    assert (
        await db_session.execute(select(Event).where(Event.id == event_c.id))
    ).scalar_one_or_none() is not None
