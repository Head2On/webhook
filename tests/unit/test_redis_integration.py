"""Unit tests for Redis integration boundary (M1 Gate 3)."""

import uuid
from unittest.mock import AsyncMock

import pytest

from app.integrations.redis import RedisClient


@pytest.mark.asyncio
async def test_redis_client_ping_when_unavailable() -> None:
    """Verify ping gracefully returns False without raising unhandled exceptions."""
    client = RedisClient(url="redis://localhost:6379/15")
    res = await client.ping()
    assert res is False
    await client.close()


@pytest.mark.asyncio
async def test_redis_client_publish_when_unavailable() -> None:
    """Verify publish gracefully returns 0 when Redis is down."""
    client = RedisClient(url="redis://localhost:6379/15")
    count = await client.publish("test_channel", "test_message")
    assert count == 0
    await client.close()


@pytest.mark.asyncio
async def test_redis_client_xadd_when_unavailable() -> None:
    """Verify xadd gracefully returns None when Redis is down."""
    client = RedisClient(url="redis://localhost:6379/15")
    entry_id = await client.xadd("test_stream", {"k": "v"})
    assert entry_id is None
    await client.close()


@pytest.mark.asyncio
async def test_redis_client_signal_outbox_event_when_unavailable() -> None:
    """Verify signal_outbox_event returns False when Redis is down."""
    client = RedisClient(url="redis://localhost:6379/15")
    signaled = await client.signal_outbox_event(
        event_id=uuid.uuid4(),
        project_id=uuid.uuid4(),
        event_type="test.event",
    )
    assert signaled is False
    await client.close()


@pytest.mark.asyncio
async def test_redis_client_mocked_operations() -> None:
    """Verify RedisClient publish, xadd, and signal_outbox_event format payloads correctly."""
    mock_redis = AsyncMock()
    mock_redis.ping.return_value = True
    mock_redis.publish.return_value = 2
    mock_redis.xadd.return_value = "1700000000000-0"

    client = RedisClient()
    client._client = mock_redis

    # Test ping
    assert await client.ping() is True
    mock_redis.ping.assert_awaited_once()

    # Test publish
    pub_count = await client.publish("channel_1", "msg_payload")
    assert pub_count == 2
    mock_redis.publish.assert_awaited_once_with("channel_1", "msg_payload")

    # Test xadd
    xadd_id = await client.xadd("stream_1", {"key1": "val1", "num": 123})
    assert xadd_id == "1700000000000-0"
    mock_redis.xadd.assert_awaited_once_with(
        "stream_1",
        {"key1": "val1", "num": "123"},
        maxlen=None,
        approximate=True,
    )

    # Test signal_outbox_event
    event_id = uuid.uuid4()
    project_id = uuid.uuid4()
    res = await client.signal_outbox_event(event_id, project_id, "order.placed")
    assert res is True

    await client.close()
