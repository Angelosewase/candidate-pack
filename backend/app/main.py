"""Application entry-point.

FastAPI app factory: mounts all routers, registers middleware, wires up the
SSE broker, and exposes the OpenAPI/Swagger docs at /docs (Redoc at /redoc).
"""

import asyncio
from contextlib import asynccontextmanager
from typing import AsyncIterator

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.api import auth, episodes, events, requests, users
from app.config import get_settings
from app.db import engine
from app.errors import DomainError
from app.events import Broker, listen_forever
from app.logging_config import AccessLogMiddleware, configure_logging

_DESCRIPTION = """
## Dataset Request Desk API

Internal platform for managing robot teleoperation dataset requests.

### Roles
| Role | Capabilities |
|---|---|
| **client** | Create requests; view only their own; accept/reject delivered requests |
| **operator** | View all requests; move through workflow; assign episodes; import CSVs |
| **admin** | Everything an operator can do, plus user management |

### Authentication
All endpoints (except `POST /auth/login`) require a **Bearer JWT** token in the
`Authorization` header. Obtain a token via `POST /auth/login`.

### Real-time events
`GET /events` is an SSE stream. Connect with an `Authorization` header (not via the
browser `EventSource` API which cannot send headers); the stream emits a JSON object
on every committed request status or assignment change.
"""

_TAGS_METADATA = [
    {
        "name": "auth",
        "description": "Login and current-user introspection.",
    },
    {
        "name": "requests",
        "description": "Dataset request lifecycle: create, view, transition status, assign episodes.",
    },
    {
        "name": "episodes",
        "description": "Episode catalogue, CSV import, import history, and analytics.",
    },
    {
        "name": "users",
        "description": "User management (admin only): list, create, update/deactivate.",
    },
    {
        "name": "events",
        "description": "Server-Sent Events stream for real-time request/assignment updates (staff only).",
    },
    {
        "name": "health",
        "description": "Liveness and readiness checks.",
    },
]


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    configure_logging(get_settings().log_level)
    broker = Broker()
    app.state.broker = broker
    listener = asyncio.create_task(listen_forever(broker, get_settings().database_url))
    yield
    listener.cancel()
    try:
        await listener
    except asyncio.CancelledError:
        pass


app = FastAPI(
    title="Dataset Request Desk",
    version="1.0.0",
    description=_DESCRIPTION,
    openapi_tags=_TAGS_METADATA,
    contact={
        "name": "Platform Engineering",
        "email": "platform@example.com",
    },
    license_info={
        "name": "Private — internal use only",
    },
    swagger_ui_parameters={"persistAuthorization": True},
    lifespan=lifespan,
)

app.add_middleware(AccessLogMiddleware)

# ---------------------------------------------------------------------------
# CORS — restrict to known origins in production via CORS_ORIGINS env var.
# The wildcard default is acceptable for local development only.
# ---------------------------------------------------------------------------
_settings = get_settings()
_allowed_origins = getattr(_settings, "cors_origins", None) or ["*"]

app.add_middleware(
    CORSMiddleware,
    allow_origins=_allowed_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ---------------------------------------------------------------------------
# Error handlers
# ---------------------------------------------------------------------------


@app.exception_handler(DomainError)
async def domain_error_handler(request: Request, exc: DomainError) -> JSONResponse:
    return JSONResponse(
        status_code=exc.status_code,
        content={"error": exc.code, "message": exc.message, "details": exc.details},
    )


# ---------------------------------------------------------------------------
# Health
# ---------------------------------------------------------------------------


@app.get(
    "/health",
    tags=["health"],
    summary="Liveness check",
    response_description="Service and database are reachable",
)
def health_check() -> dict:
    """Returns ``{\"status\": \"ok\"}`` when the API process is alive and can reach
    the database. Used by Docker healthchecks and load-balancer probes."""
    # Ping the DB so a broken connection pool surfaces here rather than on the
    # first real request.
    with engine.connect():
        pass
    return {"status": "ok"}


# ---------------------------------------------------------------------------
# Routers
# ---------------------------------------------------------------------------

app.include_router(auth.router)
app.include_router(users.router)
app.include_router(requests.router)
app.include_router(episodes.router)
app.include_router(events.router)
