"""Integration tests for IdempotencyService verifying concurrency recovery and durability."""

import asyncio
import uuid
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

from app.core.exceptions import IdempotencyFingerprintMismatchError
from app.models.idempotency import Delivery, Event, IdempotencyKey, Outbox
from app.services.idempotency import idempotency_service


@pytest.mark.asyncio
async def test_new_ingestion_creates_entities_and_returns_202(
    db_session: AsyncSession,
) -> None:
    """Verify new event commits IdempotencyKey, Event, Delivery, and Outbox before 202."""
    project_id = uuid.uuid4()
    key = "test_key_new_202"
    raw_payload = b'{"event":"order.placed","amount":100}'
    fingerprint = "jcs-rfc8785-v1:" + "f" * 64

    result = await idempotency_service.process_ingestion(
        session=db_session,
        project_id=project_id,
        idempotency_key=key,
        event_type="order.placed",
        raw_payload_bytes=raw_payload,
        fingerprint=fingerprint,
    )

    assert result.status_code == 202
    assert result.is_replay is False
    assert result.idempotency_key == key
    assert result.fingerprint == fingerprint
    assert result.response_body["status"] == "accepted"
    assert result.response_body["event_id"] == str(result.event_id)

    # Verify database persistence across all 4 entities
    key_stmt = select(IdempotencyKey).where(
        IdempotencyKey.project_id == project_id,
        IdempotencyKey.idempotency_key == key,
    )
    key_res = await db_session.execute(key_stmt)
    key_rec = key_res.scalar_one()
    assert key_rec.event_id == result.event_id
    assert key_rec.response_status_code == 202
    assert key_rec.response_body is not None

    event_stmt = select(Event).where(Event.id == result.event_id)
    event_res = await db_session.execute(event_stmt)
    event_rec = event_res.scalar_one()
    assert event_rec.raw_payload_bytes == raw_payload
    assert event_rec.event_type == "order.placed"

    deliv_stmt = select(Delivery).where(Delivery.event_id == result.event_id)
    deliv_res = await db_session.execute(deliv_stmt)
    deliv_rec = deliv_res.scalar_one()
    assert deliv_rec.status == "pending"

    outbox_stmt = select(Outbox).where(Outbox.event_id == result.event_id)
    outbox_res = await db_session.execute(outbox_stmt)
    outbox_rec = outbox_res.scalar_one()
    assert outbox_rec.status == "pending"


@pytest.mark.asyncio
async def test_identical_retry_returns_200_with_idempotent_replay_header(
    db_session: AsyncSession,
) -> None:
    """Verify duplicate submission with identical fingerprint returns 200 with replay header."""
    project_id = uuid.uuid4()
    key = "test_key_retry_200"
    raw_payload = b'{"event":"payment.received","cents":5000}'
    fingerprint = "jcs-rfc8785-v1:" + "e" * 64

    # 1. Initial submission (HTTP 202)
    res_1 = await idempotency_service.process_ingestion(
        session=db_session,
        project_id=project_id,
        idempotency_key=key,
        event_type="payment.received",
        raw_payload_bytes=raw_payload,
        fingerprint=fingerprint,
    )
    assert res_1.status_code == 202
    assert res_1.is_replay is False

    # 2. Duplicate submission with identical fingerprint (HTTP 200 OK)
    res_2 = await idempotency_service.process_ingestion(
        session=db_session,
        project_id=project_id,
        idempotency_key=key,
        event_type="payment.received",
        raw_payload_bytes=raw_payload,
        fingerprint=fingerprint,
    )
    assert res_2.status_code == 200
    assert res_2.is_replay is True
    assert res_2.response_headers.get("Idempotent-Replay") == "true"
    assert res_2.response_body == res_1.response_body
    assert res_2.event_id == res_1.event_id

    # Verify no duplicate Event was created
    events_stmt = select(Event).where(Event.project_id == project_id)
    events_res = await db_session.execute(events_stmt)
    events = events_res.scalars().all()
    assert len(events) == 1


@pytest.mark.asyncio
async def test_key_reuse_with_different_fingerprint_raises_409_conflict(
    db_session: AsyncSession,
) -> None:
    """Verify active key reused with different fingerprint raises 409 conflict error."""
    project_id = uuid.uuid4()
    key = "test_key_conflict_409"
    payload_1 = b'{"val": 1}'
    fingerprint_1 = "jcs-rfc8785-v1:" + "1" * 64
    payload_2 = b'{"val": 2}'
    fingerprint_2 = "jcs-rfc8785-v1:" + "2" * 64

    # 1. Initial submission
    res_1 = await idempotency_service.process_ingestion(
        session=db_session,
        project_id=project_id,
        idempotency_key=key,
        event_type="test.event",
        raw_payload_bytes=payload_1,
        fingerprint=fingerprint_1,
    )
    assert res_1.status_code == 202

    # 2. Reusing same active key with different fingerprint must fail with 409
    with pytest.raises(IdempotencyFingerprintMismatchError) as exc_info:
        await idempotency_service.process_ingestion(
            session=db_session,
            project_id=project_id,
            idempotency_key=key,
            event_type="test.event",
            raw_payload_bytes=payload_2,
            fingerprint=fingerprint_2,
        )

    assert exc_info.value.error_code == "IDEMPOTENCY_KEY_FINGERPRINT_MISMATCH"

    # Verify only 1 Event exists
    events_stmt = select(Event).where(Event.project_id == project_id)
    events_res = await db_session.execute(events_stmt)
    assert len(events_res.scalars().all()) == 1


@pytest.mark.asyncio
async def test_concurrent_duplicate_ingestion_handles_uniqueness_conflict(
    test_engine: AsyncEngine,
) -> None:
    """Verify concurrent requests on same key: winner gets 202, loser rolls back and gets 200."""
    session_factory = async_sessionmaker(
        bind=test_engine,
        class_=AsyncSession,
        expire_on_commit=False,
    )
    project_id = uuid.uuid4()
    key = "concurrent_key_" + uuid.uuid4().hex[:8]
    raw_payload = b'{"concurrent": true}'
    fingerprint = "jcs-rfc8785-v1:" + "c" * 64

    async def ingest_attempt() -> int:
        async with session_factory() as session:
            result = await idempotency_service.process_ingestion(
                session=session,
                project_id=project_id,
                idempotency_key=key,
                event_type="concurrent.event",
                raw_payload_bytes=raw_payload,
                fingerprint=fingerprint,
            )
            return result.status_code

    # Run two ingestion attempts concurrently
    results = await asyncio.gather(ingest_attempt(), ingest_attempt())

    assert 202 in results
    assert 200 in results

    # Verify database contains exactly 1 Event
    async with session_factory() as verify_session:
        events_stmt = select(Event).where(Event.project_id == project_id)
        events_res = await verify_session.execute(events_stmt)
        events = events_res.scalars().all()
        assert len(events) == 1


@pytest.mark.asyncio
async def test_concurrent_conflicting_fingerprint_race(
    test_engine: AsyncEngine,
) -> None:
    """Verify concurrent race with different fingerprints: winner gets 202, loser gets 409."""
    session_factory = async_sessionmaker(
        bind=test_engine,
        class_=AsyncSession,
        expire_on_commit=False,
    )
    project_id = uuid.uuid4()
    key = "concurrent_conflict_" + uuid.uuid4().hex[:8]
    payload_1 = b'{"runner": 1}'
    fingerprint_1 = "jcs-rfc8785-v1:" + "a" * 64
    payload_2 = b'{"runner": 2}'
    fingerprint_2 = "jcs-rfc8785-v1:" + "b" * 64

    async def attempt_1() -> int:
        async with session_factory() as session:
            try:
                res = await idempotency_service.process_ingestion(
                    session=session,
                    project_id=project_id,
                    idempotency_key=key,
                    event_type="race.event",
                    raw_payload_bytes=payload_1,
                    fingerprint=fingerprint_1,
                )
                return res.status_code
            except IdempotencyFingerprintMismatchError:
                return 409

    async def attempt_2() -> int:
        async with session_factory() as session:
            try:
                res = await idempotency_service.process_ingestion(
                    session=session,
                    project_id=project_id,
                    idempotency_key=key,
                    event_type="race.event",
                    raw_payload_bytes=payload_2,
                    fingerprint=fingerprint_2,
                )
                return res.status_code
            except IdempotencyFingerprintMismatchError:
                return 409

    results = await asyncio.gather(attempt_1(), attempt_2())

    assert 202 in results
    assert 409 in results

    # Verify database contains exactly 1 Event
    async with session_factory() as verify_session:
        events_stmt = select(Event).where(Event.project_id == project_id)
        events_res = await verify_session.execute(events_stmt)
        assert len(events_res.scalars().all()) == 1


@pytest.mark.asyncio
async def test_expired_key_replacement_creates_new_event(
    db_session: AsyncSession,
) -> None:
    """Verify that an expired key is retired and a new replacement Event is created (HTTP 202)."""
    project_id = uuid.uuid4()
    key = "test_expired_key_" + uuid.uuid4().hex[:8]
    now = datetime.now(UTC)

    # 1. Seed an expired key claim and event in the past
    past_key = IdempotencyKey(
        id=uuid.uuid4(),
        project_id=project_id,
        idempotency_key=key,
        fingerprint="jcs-rfc8785-v1:" + "0" * 64,
        created_at=now - timedelta(days=14),
        expires_at=now - timedelta(days=7),  # Expired 7 days ago
        retired_at=None,
    )
    db_session.add(past_key)
    await db_session.flush()

    past_event = Event(
        id=uuid.uuid4(),
        project_id=project_id,
        idempotency_key_id=past_key.id,
        event_type="old.event",
        raw_payload_bytes=b'{"old": true}',
        payload_hash=past_key.fingerprint,
        created_at=past_key.created_at,
    )
    db_session.add(past_event)
    past_key.event_id = past_event.id
    past_key.response_status_code = 202
    past_key.response_body = {"status": "accepted", "event_id": str(past_event.id)}
    await db_session.commit()

    # 2. Ingest replacement event on the same key with new payload
    new_raw_payload = b'{"new": true}'
    new_fingerprint = "jcs-rfc8785-v1:" + "9" * 64

    res = await idempotency_service.process_ingestion(
        session=db_session,
        project_id=project_id,
        idempotency_key=key,
        event_type="new.event",
        raw_payload_bytes=new_raw_payload,
        fingerprint=new_fingerprint,
    )

    # Must accept as fresh event (HTTP 202) because the previous key was expired
    assert res.status_code == 202
    assert res.is_replay is False
    assert res.event_id != past_event.id

    # 3. Verify in database: previous key is retired, new key is active
    keys_stmt = (
        select(IdempotencyKey)
        .where(
            IdempotencyKey.project_id == project_id,
            IdempotencyKey.idempotency_key == key,
        )
        .order_by(IdempotencyKey.created_at)
    )
    keys_res = await db_session.execute(keys_stmt)
    keys = keys_res.scalars().all()
    assert len(keys) == 2
    assert keys[0].id == past_key.id
    assert keys[0].retired_at is not None  # Successfully retired
    assert keys[1].id != past_key.id
    assert keys[1].retired_at is None  # Active new key
    assert keys[1].fingerprint == new_fingerprint
