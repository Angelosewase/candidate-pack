import asyncio
import json

from fastapi import APIRouter, Depends, Request
from sse_starlette.sse import EventSourceResponse

from app.deps import STAFF, get_current_user, require_roles
from app.events import Broker
from app.models import User

router = APIRouter(tags=["events"])
staff_only = require_roles(*STAFF)


@router.get("/events")
async def sse_events(
    request: Request,
    _: User = Depends(staff_only),
) -> EventSourceResponse:
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
