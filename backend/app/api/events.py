"""Server-Sent Events endpoint for real-time request/assignment updates."""

import asyncio
import json

from fastapi import APIRouter, Depends, Request
from sse_starlette.sse import EventSourceResponse

from app.deps import STAFF, get_current_user, require_roles
from app.events import Broker
from app.models import User

router = APIRouter(tags=["events"])
staff_only = require_roles(*STAFF)


@router.get(
    "/events",
    summary="Real-time event stream (SSE)",
    response_description="Server-Sent Events stream of request/assignment changes",
)
async def sse_events(
    request: Request,
    _: User = Depends(staff_only),
) -> EventSourceResponse:
    """Subscribe to live request and assignment change events (staff only).

    This endpoint uses **Server-Sent Events** (SSE) over a long-lived HTTP
    connection. Each event payload is a JSON object:

    ```json
    {"type": "request_status_changed", "request_id": 42, "client_id": 7, "status": "in_progress"}
    ```

    **Event types:**
    - `request_created` — a new request was submitted by a client.
    - `request_status_changed` — a request moved to a new status.
    - `assignments_changed` — episodes were assigned or unassigned.

    Events are published inside the same database transaction as the change, so
    they are never emitted for rolled-back operations.

    > **Note:** The browser `EventSource` API cannot send custom headers, so
    > connect via `fetch` with the `Authorization` header instead.
    """
    broker: Broker = request.app.state.broker
    queue = broker.subscribe()

    async def event_generator():
        try:
            while True:
                if await request.is_disconnected():
                    break
                event = await queue.get()
                yield {"data": json.dumps(event)}
        finally:
            broker.unsubscribe(queue)

    return EventSourceResponse(event_generator())
