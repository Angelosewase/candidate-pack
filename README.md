# Dataset Request Desk

An internal platform for managing robot teleoperation dataset requests and assignments.

## Architecture

* **Backend**: FastAPI, SQLAlchemy 2.0, PostgreSQL, Alembic
* **Frontend**: Next.js (React, TypeScript), pnpm
* **Real-time**: Server-Sent Events (SSE) backed by Postgres `LISTEN/NOTIFY`

## Running Locally

The entire system is containerised and can be booted with a single command. 

```bash
docker compose up --build
```

This command will:
1. Start PostgreSQL 16
2. Run database migrations (`alembic upgrade head`)
3. Seed the initial users
4. Start the FastAPI backend on `http://localhost:8000`
5. Start the Next.js frontend on `http://localhost:3000`

### Seed Users

The database is seeded with the following accounts (password is `ops123` for all):

* `admin@example.com` (Role: admin)
* `ops1@example.com` (Role: operator)
* `ops2@example.com` (Role: operator)
* `client-a@example.com` (Role: client)
* `client-b@example.com` (Role: client)

## Running Tests

The backend tests focus on the core domain logic: workflow constraints, assignment rules, and import idempotency.

```bash
cd backend
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python3 -m pytest tests/
```

*Note: The tests use a dedicated test database (`desk_test`) on port 55432 which is configured via the `conftest.py` fixture.*

## Stretch Goal

**Real-time** was chosen as the stretch goal. The backend uses Server-Sent Events (SSE) to push updates to the frontend. Rather than adding Redis or RabbitMQ, the message broker is implemented entirely in PostgreSQL using `LISTEN`/`NOTIFY`. Events are published within the same database transaction that modifies the data (e.g. a status change), guaranteeing that if the transaction rolls back, the event is never sent.
