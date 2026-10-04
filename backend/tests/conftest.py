"""Pytest configuration and shared fixtures.

Database setup
--------------
Tests require a **live Postgres** database called ``desk_test`` on
``localhost:55432``. This is a deliberate separate instance from the compose DB
(port 5432) so tests can't accidentally touch production-like data.

Start the test DB with::

    docker run -d --name desk_test_pg \\
        -e POSTGRES_USER=desk \\
        -e POSTGRES_DB=desk_test \\
        -p 55432:5432 \\
        postgres:16-alpine

Transaction isolation strategy
-------------------------------
Each test runs inside a SAVEPOINT (nested transaction) on top of an outer
connection-level transaction that is rolled back after the test. This gives
full isolation without recreating the schema on every test (only on every
session), and is safe with SQLAlchemy's ``expire_on_commit=False`` because the
session never actually commits to the DB.
"""

import os

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, event, text
from sqlalchemy.orm import Session, sessionmaker

# Must be set before importing app modules so ``get_settings()`` / ``create_engine``
# in db.py pick up the test URL.
os.environ["DATABASE_URL"] = "postgresql+psycopg://desk@localhost:55432/desk_test"
os.environ["JWT_SECRET"] = "test-only-secret"
os.environ["ENVIRONMENT"] = "development"

from app.models import Base  # noqa: E402 — import after env is set
from app.main import app  # noqa: E402
from app.db import get_db  # noqa: E402

# ---------------------------------------------------------------------------
# Session-scoped engine: create / drop schema once per pytest run.
# ---------------------------------------------------------------------------

_engine = create_engine(
    os.environ["DATABASE_URL"],
    pool_pre_ping=True,
    # Keep connections alive across the session to use the same outer tx.
    pool_size=2,
)
_TestingSessionLocal = sessionmaker(bind=_engine, autoflush=False, expire_on_commit=False)


@pytest.fixture(scope="session", autouse=True)
def _create_schema():
    """Drop and recreate the full schema once per test session."""
    Base.metadata.drop_all(bind=_engine)
    Base.metadata.create_all(bind=_engine)
    # Seed the robots table that the migration normally inserts.
    with _engine.begin() as conn:
        conn.execute(
            text(
                "INSERT INTO robots (robot_id) VALUES "
                "('arm-01'),('arm-02'),('arm-03'),('mobile-01'),('humanoid-01') "
                "ON CONFLICT DO NOTHING"
            )
        )
    yield
    Base.metadata.drop_all(bind=_engine)


# ---------------------------------------------------------------------------
# Function-scoped DB fixture: wraps each test in a savepoint.
# ---------------------------------------------------------------------------


@pytest.fixture
def db():
    """Isolated database session for one test.

    Begins a connection-level transaction, yields a session bound to that
    connection, then rolls back — so each test starts from the same clean state
    without touching the underlying schema.
    """
    connection = _engine.connect()
    # Outer transaction: rolled back at the end of the test.
    transaction = connection.begin()
    session = _TestingSessionLocal(bind=connection)

    # SQLAlchemy's ``session.commit()`` would normally issue a real COMMIT.
    # We intercept it to flush instead, so service-layer code that calls
    # ``db.commit()`` doesn't escape our outer rollback.
    @event.listens_for(session, "after_transaction_end")
    def _restart_savepoint(session, transaction):
        if transaction.nested and not transaction._parent.nested:
            session.begin_nested()

    session.begin_nested()  # SAVEPOINT

    yield session

    session.close()
    transaction.rollback()
    connection.close()


# ---------------------------------------------------------------------------
# Function-scoped HTTP test client.
# ---------------------------------------------------------------------------


@pytest.fixture
def client(db: Session):
    """FastAPI TestClient whose DB dependency is replaced with the test session."""

    def _override_get_db():
        yield db

    app.dependency_overrides[get_db] = _override_get_db
    with TestClient(app, raise_server_exceptions=True) as c:
        yield c
    app.dependency_overrides.pop(get_db, None)
