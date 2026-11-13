import asyncio
import json
import logging
from collections import defaultdict
from collections.abc import Iterable
from datetime import UTC, datetime
from typing import Any
from uuid import UUID

import asyncpg
import redis.asyncio as redis
from redis.exceptions import RedisError

logger = logging.getLogger(__name__)

CHANNEL_PREFIX = "eventhub:seats:"
CLIENT_QUEUE_SIZE = 256
PUBLISH_TIMEOUT_SECONDS = 2
MAX_RECONNECT_DELAY_SECONDS = 30


def server_time() -> str:
    return datetime.now(UTC).isoformat()


def _resync_message(event_id: UUID) -> str:
    return json.dumps(
        {"type": "resync", "event_id": str(event_id), "server_time": server_time()}
    )


class SeatRealtimeHub:
    """Connects local WebSocket clients to Redis Pub/Sub across API instances."""

    def __init__(self, redis_client: redis.Redis) -> None:
        self._redis = redis_client
        self._clients: defaultdict[UUID, set[asyncio.Queue[str]]] = defaultdict(set)

    def connect(self, event_id: UUID) -> asyncio.Queue[str]:
        queue: asyncio.Queue[str] = asyncio.Queue(maxsize=CLIENT_QUEUE_SIZE)
        self._clients[event_id].add(queue)
        return queue

    def disconnect(self, event_id: UUID, queue: asyncio.Queue[str]) -> None:
        clients = self._clients.get(event_id)
        if clients is None:
            return
        clients.discard(queue)
        if not clients:
            del self._clients[event_id]

    async def publish(self, event_id: UUID, payload: dict[str, Any]) -> None:
        try:
            await asyncio.wait_for(
                self._redis.publish(f"{CHANNEL_PREFIX}{event_id}", json.dumps(payload)),
                timeout=PUBLISH_TIMEOUT_SECONDS,
            )
        except (RedisError, OSError, TimeoutError):
            # The booking is already committed, so it must not fail here.
            logger.warning("Could not publish a realtime update for event %s", event_id)

    async def run(self) -> None:
        delay = 1
        connected_before = False

        while True:
            pubsub = self._redis.pubsub(ignore_subscribe_messages=True)
            try:
                await pubsub.psubscribe(f"{CHANNEL_PREFIX}*")
                if connected_before:
                    self._request_resync_for_all()
                connected_before = True
                delay = 1

                async for message in pubsub.listen():
                    if message["type"] == "pmessage":
                        self._handle_message(message["channel"], message["data"])
            except asyncio.CancelledError:
                raise
            except (RedisError, OSError, TimeoutError):
                logger.warning("Redis subscription lost; retrying in %s seconds", delay)
            finally:
                try:
                    await pubsub.aclose()
                except (RedisError, OSError, TimeoutError):
                    pass

            await asyncio.sleep(delay)
            delay = min(delay * 2, MAX_RECONNECT_DELAY_SECONDS)

    def _handle_message(self, channel: str, data: str) -> None:
        try:
            event_id = UUID(channel.removeprefix(CHANNEL_PREFIX))
        except ValueError:
            logger.warning("Ignoring message from unexpected channel %s", channel)
            return

        for queue in list(self._clients.get(event_id, ())):
            self._deliver(event_id, queue, data)

    @staticmethod
    def _deliver(event_id: UUID, queue: asyncio.Queue[str], text: str) -> None:
        try:
            queue.put_nowait(text)
        except asyncio.QueueFull:
            # A slow client gets one instruction to reload the current state.
            while not queue.empty():
                queue.get_nowait()
            queue.put_nowait(_resync_message(event_id))

    def _request_resync_for_all(self) -> None:
        for event_id, queues in list(self._clients.items()):
            message = _resync_message(event_id)
            for queue in list(queues):
                self._deliver(event_id, queue, message)


async def publish_seat_state(
    pool: asyncpg.Pool,
    hub: SeatRealtimeHub,
    event_id: UUID,
    event_seat_ids: Iterable[UUID],
    reason: str,
) -> None:
    """Broadcast committed seat state, without exposing who holds a seat."""
    seat_ids = list(event_seat_ids)
    if not seat_ids:
        return

    try:
        rows = await pool.fetch(
            """
            SELECT id, status, hold_expires_at
            FROM event_seats
            WHERE event_id = $1 AND id = ANY ($2::uuid[])
            """,
            event_id,
            seat_ids,
        )
    except (asyncpg.PostgresError, asyncpg.InterfaceError, OSError):
        logger.warning("Could not load seat state for event %s", event_id)
        return

    await hub.publish(
        event_id,
        {
            "type": "seats.updated",
            "event_id": str(event_id),
            "reason": reason,
            "server_time": server_time(),
            "seats": [
                {
                    "event_seat_id": str(row["id"]),
                    "status": row["status"],
                    "hold_expires_at": (
                        row["hold_expires_at"].isoformat() if row["hold_expires_at"] else None
                    ),
                }
                for row in rows
            ],
        },
    )


async def expire_holds_loop(
    pool: asyncpg.Pool, hub: SeatRealtimeHub, interval_seconds: float
) -> None:
    while True:
        try:
            rows = await pool.fetch(
                "SELECT expired_event_id, expired_seat_id FROM release_expired_holds()"
            )
            seats_by_event: defaultdict[UUID, list[UUID]] = defaultdict(list)
            for row in rows:
                seats_by_event[row["expired_event_id"]].append(row["expired_seat_id"])

            for event_id, seat_ids in seats_by_event.items():
                await publish_seat_state(pool, hub, event_id, seat_ids, "expired")
        except Exception:
            logger.exception("Expired-hold sweep failed")

        await asyncio.sleep(interval_seconds)