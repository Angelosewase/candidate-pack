"""Episode catalogue, CSV import, import history, and analytics endpoints."""

from datetime import date
from typing import Annotated

from fastapi import APIRouter, Depends, File, Query, UploadFile
from sqlalchemy.orm import Session

from app.config import get_settings
from app.db import get_db
from app.deps import STAFF, get_current_user, require_roles
from app.errors import InvalidInput, PayloadTooLarge
from app.models import Quality, User
from app.schemas import AnalyticsOut, EpisodeOut, ImportRunOut, Page
from app.services import analytics as analytics_service
from app.services import episodes as episode_service
from app.services import importer

router = APIRouter(tags=["episodes"])
staff_only = require_roles(*STAFF)


@router.get(
    "/episodes",
    response_model=Page[EpisodeOut],
    summary="List episodes",
    response_description="Paginated episode catalogue with active assignment info",
)
def list_episodes(
    task_name: str | None = Query(default=None, description="Filter by exact task name"),
    quality: Quality | None = Query(default=None, description="Filter by quality grade"),
    robot_id: str | None = Query(default=None, description="Filter by robot ID"),
    assignable_only: bool = Query(
        default=False,
        description="When true, return only unassigned good/usable episodes",
    ),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    db: Session = Depends(get_db),
    _: User = Depends(staff_only),
) -> Page[EpisodeOut]:
    """List episodes (staff only).

    Each episode in the response includes `assigned_request_id` — the ID of the
    request it is currently assigned to, or `null` if unassigned.

    Use `assignable_only=true` to show only episodes that can be immediately
    assigned to a request (unassigned, graded good or usable).
    """
    rows = episode_service.list_episodes(
        db,
        task_name=task_name,
        quality=quality,
        robot_id=robot_id,
        assignable_only=assignable_only,
        limit=limit + 1,
        offset=offset,
    )
    items = [
        EpisodeOut.model_validate({**EpisodeOut.model_validate(e).model_dump(), "assigned_request_id": r})
        for e, r in rows[:limit]
    ]
    return Page(items=items, limit=limit, offset=offset, has_more=len(rows) > limit)


@router.post(
    "/import",
    status_code=201,
    summary="Import episodes from CSV",
    response_description="Import report with inserted/updated/unchanged/skipped counts",
)
async def import_csv(
    file: UploadFile = File(..., description="CSV file with episode metadata"),
    db: Session = Depends(get_db),
    user: User = Depends(staff_only),
) -> dict:
    """Import episodes from a CSV file (staff only). Safe to run multiple times
    against the same file — idempotent on `episode_id`.

    **Expected CSV columns** (order-independent, extra columns are ignored):

    | Column | Required | Notes |
    |---|---|---|
    | `episode_id` | ✓ | Must match `EP-<digits>` |
    | `robot_id` | ✓ | Must be a known robot |
    | `task_name` | ✓ | Normalised to lowercase |
    | `recorded_at` | ✓ | ISO 8601 or DD/MM/YYYY |
    | `duration_seconds` | — | Stored as NULL if missing |
    | `operator_name` | — | Stored as NULL if missing |
    | `quality` | ✓ | `good`, `usable`, or `bad` |

    The response reports counts of inserted, updated, unchanged, and skipped rows,
    plus per-row skip reasons. Duplicate `episode_id`s within the file are handled
    conservatively (see `NOTES.md`).

    - File must be UTF-8 encoded (UTF-8 BOM from Excel is tolerated).
    - Size limit: `MAX_IMPORT_BYTES` (default 50 MB).
    """
    max_bytes = get_settings().max_import_bytes
    data = await file.read()
    if len(data) > max_bytes:
        raise PayloadTooLarge(
            f"File is {len(data)} bytes; limit is {max_bytes} bytes",
            details={"size_bytes": len(data), "limit_bytes": max_bytes},
        )
    text = importer.decode_upload(data)
    return importer.import_episodes(db, text, filename=file.filename or "upload.csv", uploaded_by=user.id)


@router.get(
    "/imports",
    response_model=list[ImportRunOut],
    summary="List recent import runs",
    response_description="Most recent CSV import summaries, newest first",
)
def list_imports(
    limit: int = Query(20, ge=1, le=100, description="Number of import runs to return"),
    db: Session = Depends(get_db),
    _: User = Depends(staff_only),
) -> list[ImportRunOut]:
    """Return a summary of the most recent CSV import runs (staff only).

    Each entry shows the file name, row counts, and timestamp. For the full
    per-row skip report, re-run the import or check the database directly.
    """
    runs = episode_service.list_import_runs(db, limit=limit)
    return [
        ImportRunOut(
            id=r.id,
            filename=r.filename,
            total_rows=r.total_rows,
            inserted=r.inserted,
            updated=r.updated,
            unchanged=r.unchanged,
            skipped=r.skipped,
            created_at=r.created_at,
        )
        for r in runs
    ]


@router.get(
    "/analytics",
    response_model=AnalyticsOut,
    summary="Analytics aggregations",
    response_description="In-DB aggregated statistics for the given date range",
)
def get_analytics(
    date_from: date = Query(description="Inclusive start date (UTC, YYYY-MM-DD)"),
    date_to: date = Query(description="Inclusive end date (UTC, YYYY-MM-DD)"),
    db: Session = Depends(get_db),
    _: User = Depends(staff_only),
) -> AnalyticsOut:
    """Return analytics for a given UTC date range (staff only).

    All aggregations run as single SQL queries in Postgres (no Python-side loops):

    - **episodes_per_day**: episode count per calendar day per robot.
    - **request_fulfilment**: request counts by status + median hours from
      submission to first delivery (using `percentile_cont` in Postgres).
    - **top_tasks_by_good_episodes**: top 5 task names by good-episode count.

    At 5 million episodes, the covering index on `(recorded_at) INCLUDE (robot_id,
    task_name, quality)` keeps the episode queries to index-only scans.
    """
    if date_from > date_to:
        raise InvalidInput("date_from must not be after date_to")
    return analytics_service.get_analytics(db, date_from, date_to)
