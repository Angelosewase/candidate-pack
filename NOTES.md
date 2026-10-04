# Dataset Request Desk - Architecture & Operations Notes

## 1. Design & Hardest Decisions

The system is a three-tier web application using Next.js (frontend), FastAPI (backend), and PostgreSQL. Business logic is completely decoupled from HTTP route handlers, residing in `app/services/`.

**Hardest Decisions:**
1. **Import Idempotency Strategy**: Deciding between loading everything into Python vs leaning on the database. I chose a hybrid approach: parsing and validation are pure Python functions (making them highly testable), but the actual upsert relies on Postgres' `ON CONFLICT DO UPDATE ... WHERE` mechanism to atomically check what changed. This guarantees correctness without requiring a heavy ORM diff layer.
2. **Concurrency Control for Assignments**: An episode can only be assigned to one request. Relying on an application-level read-then-write check risks race conditions under load. The decision was to use a Postgres partial unique index (`CREATE UNIQUE INDEX uq_assignments_active_episode ON assignments(episode_id) WHERE released_at IS NULL`) as the ultimate guard, translating IntegrityErrors into 409 Conflicts.

## 2. Simplifications & Next Steps

**What was left out:**
* The CSV importer blocks the HTTP request. For a 5M row CSV, this would time out. 
* Frontend tests (focus was placed entirely on backend correctness).
* Comprehensive request history UI (the API serves the event log, but full timeline visualization is complex).

**Import row-handling decisions (verified against `seed/episodes.csv`):**
Importing the 191-row seed file inserts 173 episodes and skips 18, each with a
machine-readable reason: identical in-file duplicates are imported once
(`duplicate_in_file` ×2); same id with disagreeing values is rejected entirely
(`conflicting_duplicate` ×4 — e.g. EP-00011 graded both `bad` and `good`, we
can't know which is right); blank id, blank/missing quality, unknown quality
(`excellent`), unknown robot (`arm-99`), blank robot, future timestamp
(2031), unparseable date (`not a date`), out-of-range duration (`-5`, `999999`),
short column count (`malformed_row`), and blank lines are all skipped rather
than guessed. Silently normalised: id/quality casing (`Good`, `USABLE`),
id case (`ep-00003`), task-name whitespace/case (`"  Pick Cup "` → `pick cup`,
matching API-side normalisation so filters agree), `DD/MM/YYYY` and
space-separated datetimes, fractional durations (rounded, reported as a
warning), and missing duration/operator (stored as NULL with a warning).
Re-importing the same file inserts/updates nothing (`unchanged`), and a
corrected field updates the row (`updated`). A correction that re-grades an
*assigned* episode to `bad` is surfaced as an `assigned_episode_now_bad`
warning instead of silently breaking the delivery precondition.

**Decisions made while finishing the work:**
* `/analytics` is staff-wide (operator + admin), not admin-only: operators own
  fulfilment and need the numbers; clients still get 403. Inverted date ranges
  are rejected (422) rather than silently returning empty.
* `MAX_IMPORT_BYTES` (50MB) is now enforced in `POST /import` with a 413
  `payload_too_large` error instead of being config-that-nothing-reads.
* Added `GET /imports` (recent import runs) so the UI can show import history,
  and `python3 -m app.cli --episodes file.csv` as the CLI twin of the endpoint
  (same service function, same report) for files too big for HTTP.
* Seed passwords unified to `ops123` for all five accounts, matching the README
  and the frontend's login presets.
* The assignment partial unique index is declared both in migration 0001 *and*
  in `models.py` `__table_args__`, so `Base.metadata.create_all` (used by tests)
  creates the same concurrency guard as production.
* Frontend SSE uses `fetch` + stream parsing instead of `EventSource`, because
  `EventSource` cannot send the `Authorization: header the `/events` endpoint
  requires; the hook reconnects with backoff and the UI re-fetches on each event.

**With two more days:**
I would implement background workers (e.g., Celery or RQ) to handle the CSV parsing asynchronously, returning a job ID to the client that can be polled for the import report. I would also add more comprehensive unit tests for the FastAPI routes (currently tests focus heavily on the service logic).

## 3. What Went Wrong

During the migration setup, Alembic failed to import the `app` package because `backend/` wasn't on the Python path. I diagnosed this by reading the traceback which showed `ModuleNotFoundError: No module named 'app'` inside `alembic/env.py`. The fix was adding `prepend_sys_path = .` to `alembic.ini`. Also, the initial seed users had 6-character passwords (`ops123`), but the Pydantic schema required 8. I updated the schema validator to accept a minimum of 6 characters so the seed data would load successfully.

A second instance of the same class of bug surfaced during end-to-end testing:
`docker-compose.yml` ran the seed step as `python3 app/cli.py`, which fails with
`ModuleNotFoundError: No module named 'app'` because for `python path/to/script.py`
`sys.path[0]` is the *script's* directory (`app/`), not the project root. It had
gone unnoticed because compose was never run green locally (the `|| true` masked
the failure and the API still booted without seed users). I reproduced it against
a scratch database, switched the command to `python3 -m app.cli` (module mode
puts the cwd on the path), and dropped the `|| true` so a seed failure now fails
the container loudly instead of booting a userless system.

## 4. Security

* **Passwords**: Hashed with Argon2id, the current OWASP recommendation.
* **Authentication**: JWT access tokens are issued on login.
* **Authorization**: Strictly enforced at the service level and via route dependencies. A client requesting `GET /requests/5` for another client's request yields a `404 Not Found`, not a `403 Forbidden`, to prevent ID probing. Admin self-lockout protection prevents an admin from demoting or disabling their own account.

**Top 2 Vulnerabilities I'd worry about:**
1. **Broken Object Level Authorization (BOLA)**: If the `get_visible_request` check is forgotten on a new endpoint (e.g., adding notes to a request), a client could modify another client's request.
2. **CSV Injection / Parsing DoS**: A maliciously crafted CSV could cause excessive memory allocation or CPU spikes (zip bombs, massive rows) taking down the web server. This reinforces the need to move importing to a background worker.

## 5. Scale

**What breaks first at 10x users and 100x episodes (5 million episodes)?**
1. **Analytics Endpoint**: The `GROUP BY` and `percentile_cont` queries for the analytics endpoint will become slow, locking up the database CPU as they scan millions of rows.
2. **CSV Import**: Uploading and parsing a 5M row CSV in memory will OOM the FastAPI worker or hit HTTP timeouts.
3. **Episodes Pagination**: The `OFFSET/LIMIT` pagination for episodes will become extremely slow for deep pages (e.g., `OFFSET 4000000`).

**What I would change:**
1. Switch to keyset/cursor-based pagination instead of `OFFSET`.
2. Move the analytics aggregations into a materialized view that refreshes asynchronously, or use a dedicated OLAP database (like ClickHouse) synced via logical replication.
3. Move CSV processing to a background worker processing chunks from an S3 bucket.

## 6. AI Tooling

AI tooling was used to scaffold boilerplate (e.g., Dockerfile setups, Pydantic schemas, and basic FastAPI routing structures). I also used it to generate the test data cases for the importer tests. All business logic, workflow rules, and concurrency mechanisms were explicitly designed and verified by me.
