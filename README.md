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

The API talks to `DATABASE_URL` and the UI talks to `NEXT_PUBLIC_API_URL`
(defaults to `http://localhost:8000` in `docker-compose.yml`).

### Seed Users

The database is seeded with the following accounts (password is `ops123` for all):

* `admin@example.com` (Role: admin)
* `ops1@example.com` (Role: operator)
* `ops2@example.com` (Role: operator)
* `client-a@example.com` (Role: client)
* `client-b@example.com` (Role: client)

### Useful endpoints

* `GET /health` — liveness check.
* `POST /import` — staff-only episode CSV import (multipart upload, 50MB limit,
  idempotent; returns inserted/updated/unchanged/skipped + per-row reasons).
  The same logic is available as a CLI: `python3 -m app.cli --episodes path/to.csv`
  (run from `backend/`).
* `GET /imports` — staff-only recent import history.
* `GET /analytics?date_from=…&date_to=…` — staff-only (operator + admin) in-DB
  aggregations: episodes/day/robot, fulfilment by status + median
  submitted→delivered hours, top-5 tasks by good episodes.
* `GET /events` — staff-only SSE stream of committed request/assignment changes.

## Running Tests

Backend tests need a **live Postgres** for the dedicated `desk_test` database on
`localhost:55432` (hardcoded in `backend/tests/conftest.py`, separate from the
compose DB on 5432). They focus on the core domain rules: workflow transitions,
assignment rules, authorization, and import idempotency.

```bash
cd backend
pip install -r requirements-dev.txt  # pytest lives here, not in requirements.txt
python3 -m pytest tests/ -x -q
python3 -m pytest tests/test_workflow.py -q  # single file
```

Frontend checks (run in `frontend/`, uses **pnpm**, not npm):

```bash
pnpm run typecheck
pnpm run lint
pnpm run build
```

## Stretch Goal

**Real-time** was chosen as the stretch goal. The backend uses Server-Sent Events (SSE) to push updates to the frontend. Rather than adding Redis or RabbitMQ, the message broker is implemented entirely in PostgreSQL using `LISTEN`/`NOTIFY`. Events are published within the same database transaction that modifies the data (e.g. a status change), guaranteeing that if the transaction rolls back, the event is never sent. The frontend subscribes with `fetch` (so it can send the `Authorization` header, which `EventSource` cannot) and re-fetches state on every event; operators see a "live" indicator plus a banner naming the changed request.

## Scale notes (5M episodes)

Analytics stays in Postgres (`GROUP BY` + `percentile_cont`, no Python-side loops)
over a covering index on `episodes(recorded_at) INCLUDE (robot_id, task_name, quality)`,
so the hot queries are index-only scans; at 5M rows they are still single-digit-second
range scans, and the documented next step is a materialized view / OLAP replica.
CSV import is an idempotent DB upsert (`ON CONFLICT … WHERE … IS DISTINCT FROM`)
in 1000-row batches inside one transaction, capped at 50MB per HTTP request —
a 5M-row file must go through the CLI/chunked path, not the request thread.
Episode browsing uses `LIMIT/OFFSET` today (fine for staff paging); deep pages get
slow past ~1M rows and should move to keyset pagination. See `NOTES.md` §5.
