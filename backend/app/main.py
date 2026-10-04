import asyncio
from contextlib import asynccontextmanager
from typing import AsyncIterator

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.api import auth, episodes, events, requests, users
from app.config import get_settings
from app.errors import DomainError
from app.events import Broker, listen_forever
from app.logging_config import AccessLogMiddleware, configure_logging


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


app = FastAPI(title="Dataset Request Desk", lifespan=lifespan)
app.add_middleware(AccessLogMiddleware)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.exception_handler(DomainError)
async def domain_error_handler(request: Request, exc: DomainError) -> JSONResponse:
    return JSONResponse(
        status_code=exc.status_code,
        content={"error": exc.code, "message": exc.message, "details": exc.details},
    )


@app.get("/health", tags=["health"])
def health_check() -> dict:
    return {"status": "ok"}


app.include_router(auth.router)
app.include_router(users.router)
app.include_router(requests.router)
app.include_router(episodes.router)
app.include_router(events.router)
