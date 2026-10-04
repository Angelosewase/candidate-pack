# Dataset Request Desk - Architecture & Operations Notes

## Architecture Overview

The system is built as a three-tier web application:
1. **Frontend**: Next.js with React (built by the user).
2. **Backend**: FastAPI with Python 3.14. Business logic is separated into standalone service functions rather than being mixed into HTTP route handlers.
3. **Database**: PostgreSQL 16 serving as the source of truth, queue, and event broker.

## Design Decisions

- **Idempotent Imports**: The CSV importer is pure and does not touch the database until validation is complete. We use PostgreSQL's `ON CONFLICT DO UPDATE` with a comparison on `xmax = 0` to only update rows that have genuinely changed, keeping an exact count of inserted vs. updated vs. unchanged rows. Identical duplicates within a file are collapsed, while conflicting duplicates (e.g. same episode graded good and bad simultaneously) are quarantined to prevent non-deterministic data overwriting.
- **State Machine**: Request states are strictly constrained by a central `workflow.py` definition that controls which roles can execute which transitions.
- **Real-Time Updates via Postgres Listen/Notify**: Instead of deploying Redis or RabbitMQ, we use PostgreSQL's native `LISTEN`/`NOTIFY` commands. Events are emitted within the same transaction that modifies the data (`app/events.py`). If a transaction rolls back, the event is never sent. This guarantees strong consistency between the SSE broadcast and the database state without adding infrastructure complexity.
- **Analytics in the Database**: All aggregations, percentiles (`percentile_cont`), and temporal joins (time to delivery) are written as native SQL executed entirely in Postgres. The backend only shapes the results for JSON serialization.

## Security

- **Authentication**: JWT access tokens are issued on login.
- **Passwords**: Hashed with Argon2id, the current OWASP recommendation for password storage.
- **Authorisation**: 
  - Role-based decorators prevent unauthorised route access. 
  - The `get_visible_request` query inherently returns a 404 for a client trying to access another client's request, preventing identifier probing (403 would reveal existence).
- **Admin Lockout**: Admin accounts cannot deactivate themselves or downgrade their own role, preventing accidental system lockouts.

## Concurrency Control & Scale

- **Concurrency on Assignments**: To prevent a race condition where the same episode is assigned to two requests simultaneously by two operators, we rely on a partial unique index in Postgres: `CREATE UNIQUE INDEX uq_assignments_active_episode ON assignments(episode_id) WHERE released_at IS NULL`. Application-level checks handle UX, but this database constraint guarantees correctness under load.
- **Row Locks**: State transitions on requests take a row-level lock (`SELECT ... FOR UPDATE`) before checking preconditions and making changes. This serializes operations (like a concurrent delivery and rejection).

## Running the Application

Requirements: Docker and Docker Compose.

```bash
docker compose up --build
```

This will automatically:
1. Boot PostgreSQL.
2. Run database schema migrations (`alembic`).
3. Seed the initial users from `seed/users.json`.
4. Start the FastAPI backend on http://localhost:8000.
5. Start the Next.js frontend on http://localhost:3000.

## Running Tests

Tests are written with pytest and focus on the core rules (workflow constraints, import validation logic). Ensure your virtual environment is active and dependencies are installed.

```bash
cd backend
python3 -m pytest tests/
```
