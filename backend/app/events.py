"""Real-time request events (stretch item: SSE).

Publishing uses Postgres ``pg_notify`` *inside the same transaction* as the change, so
Postgres only delivers the notification if that transaction commits: listeners never
see an event for a change that was rolled back. Each API process holds one LISTEN
connection and fans events out to its SSE subscribers, so this works with several
API workers/replicas without adding Redis.
"""

import asyncio
import json
import logging

import psycopg
from sqlalchemy import text
from sqlalchemy.engine import make_url
from sqlalchemy.orm import Session

from app.models import DatasetRequest

log = logging.getLogger(__name__)

CHANNEL = "request_events"


def publish(db: Session, event_type: str, request: DatasetRequest) -> None:
    payload = {
        "type": event_type,
        "request_id": request.id,
        "client_id": request.client_id,
        "status": request.status.value,
    }
    db.execute(text("SELECT pg_notify(:channel, :payload)"), {
        "channel": CHANNEL,
        "payload": json.dumps(payload),
    })


class Broker:
    """In-process fan-out from the single LISTEN connection to SSE subscribers."""

    def __init__(self) -> None:
        self._subscribers: set[asyncio.Queue[dict]] = set()

    def subscribe(self) -> asyncio.Queue[dict]:
        queue: asyncio.Queue[dict] = asyncio.Queue(maxsize=100)
        self._subscribers.add(queue)
        return queue

    def unsubscribe(self, queue: asyncio.Queue[dict]) -> None:
        self._subscribers.discard(queue)

    def publish(self, event: dict) -> None:
        for queue in list(self._subscribers):
            try:
                queue.put_nowait(event)
            except asyncio.QueueFull:
                # A stuck client must not block everyone else. Events only tell the UI
                # *what* changed; it re-fetches state, so a dropped event is recoverable.
                log.warning("sse_subscriber_queue_full")


def _libpq_dsn(sqlalchemy_url: str) -> str:
    return make_url(sqlalchemy_url).set(drivername="postgresql").render_as_string(
        hide_password=False
    )


async def listen_forever(broker: Broker, database_url: str) -> None:
    dsn = _libpq_dsn(database_url)
    while True:
        try:
            async with await psycopg.AsyncConnection.connect(dsn, autocommit=True) as conn:
                await conn.execute(f"LISTEN {CHANNEL}")
                log.info("event_listener_connected")
                async for notification in conn.notifies():
                    try:
                        broker.publish(json.loads(notification.payload))
                    except json.JSONDecodeError:
                        log.warning("event_listener_bad_payload")
        except asyncio.CancelledError:
            raise
        except Exception:
            log.exception("event_listener_error; reconnecting in 2s")
            await asyncio.sleep(2)
