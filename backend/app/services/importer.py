"""Episode CSV import.

Two stages:

1. ``parse_csv`` - pure function: validates and normalises every row and decides what
   to skip and why. No database access, so every rule is unit-testable.
2. ``import_episodes`` - upserts the valid rows keyed on ``episode_id`` and records an
   ``import_runs`` row with the full report.

Idempotency: re-running the same file inserts nothing and updates nothing; rows are
reported as ``unchanged``. If the recording system later corrects a field, re-importing
updates that episode (it is the source of truth) and reports it as ``updated``.

Row handling policy (see NOTES.md for the reasoning):

* skip the row - anything that would make the episode wrong for assignment or analytics:
  missing/invalid id, unknown or missing robot, missing task, unparseable or future
  timestamp, missing or unrecognised quality, impossible duration, wrong column count.
* import with a warning - descriptive fields that are merely missing (duration, operator
  name) are stored as NULL; fractional durations are rounded.
* normalise silently - whitespace, casing of ids/robots/tasks/quality, ISO variants.
* duplicates inside one file - identical rows are imported once; rows sharing an id but
  disagreeing on any value are *all* skipped, because we cannot know which is correct
  (e.g. the same episode graded both 'good' and 'bad').
"""

import csv
import hashlib
import io
import math
import re
from collections import Counter
from collections.abc import Iterable, Iterator
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime, timedelta

from sqlalchemy import func, literal_column, select, tuple_
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.orm import Session

from app.errors import InvalidInput
from app.models import Assignment, Episode, ImportRun, Quality, Robot
from app.normalize import normalize_task_name

COLUMNS = (
    "episode_id",
    "robot_id",
    "task_name",
    "recorded_at",
    "duration_seconds",
    "operator_name",
    "quality",
)
UPDATABLE = COLUMNS[1:]
EPISODE_ID_RE = re.compile(r"^EP-\d{1,12}$")
MAX_DURATION_SECONDS = 3600  # episodes are short clips; anything longer is corrupt data
MISSING_MARKERS = {"", "n/a", "na", "null", "none", "-"}
DAY_FIRST_FORMATS = ("%d/%m/%Y %H:%M", "%d/%m/%Y %H:%M:%S", "%d/%m/%Y")
CHUNK_SIZE = 1000


@dataclass
class RowIssue:
    row: int  # spreadsheet-style row number; the header is row 1
    episode_id: str | None
    reason: str
    detail: str


@dataclass
class ParsedEpisode:
    row: int
    episode_id: str
    robot_id: str
    task_name: str
    recorded_at: datetime
    duration_seconds: int | None
    operator_name: str | None
    quality: Quality
    warnings: list[RowIssue] = field(default_factory=list)

    def values(self) -> tuple:
        return tuple(getattr(self, c) for c in COLUMNS)


@dataclass
class ParseResult:
    total_rows: int
    episodes: list[ParsedEpisode]
    skipped: list[RowIssue]

    @property
    def warnings(self) -> list[RowIssue]:
        return [w for e in self.episodes for w in e.warnings]


class _RowError(Exception):
    def __init__(self, reason: str, detail: str) -> None:
        self.reason = reason
        self.detail = detail
        self.episode_id: str | None = None  # filled in once the id itself has parsed


# --- field parsers ------------------------------------------------------------------


def _is_missing(value: str) -> bool:
    return value.strip().lower() in MISSING_MARKERS


def parse_episode_id(raw: str) -> str:
    value = raw.strip().upper()
    if not value:
        raise _RowError("missing_episode_id", "episode_id is blank")
    if not EPISODE_ID_RE.match(value):
        raise _RowError("invalid_episode_id", f"'{raw}' is not of the form EP-<digits>")
    return value


def parse_robot_id(raw: str, known_robots: set[str]) -> str:
    value = raw.strip().lower()
    if not value:
        raise _RowError("missing_robot_id", "robot_id is blank")
    if value not in known_robots:
        raise _RowError("unknown_robot", f"robot '{value}' is not a known robot")
    return value


def parse_task_name(raw: str) -> str:
    value = normalize_task_name(raw)
    if not value:
        raise _RowError("missing_task_name", "task_name is blank")
    return value


def parse_recorded_at(raw: str, now: datetime) -> datetime:
    """Accepts ISO 8601 variants and day-first DD/MM/YYYY. Naive timestamps are UTC."""
    value = raw.strip()
    if not value:
        raise _RowError("missing_recorded_at", "recorded_at is blank")
    parsed: datetime | None = None
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError:
        for fmt in DAY_FIRST_FORMATS:
            try:
                parsed = datetime.strptime(value, fmt)
                break
            except ValueError:
                continue
    if parsed is None:
        raise _RowError("invalid_recorded_at", f"'{raw}' is not a recognised date/time")
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=UTC)
    parsed = parsed.astimezone(UTC)
    if parsed > now + timedelta(minutes=5):  # small allowance for clock skew
        raise _RowError("future_recorded_at", f"'{raw}' is in the future")
    return parsed


def parse_duration(raw: str, row: int, episode_id: str) -> tuple[int | None, list[RowIssue]]:
    if _is_missing(raw):
        return None, [RowIssue(row, episode_id, "missing_duration", "stored as NULL")]
    try:
        number = float(raw.strip())
    except ValueError:
        raise _RowError("invalid_duration", f"'{raw}' is not a number") from None
    if not math.isfinite(number):
        raise _RowError("invalid_duration", f"'{raw}' is not a number")
    warnings = []
    seconds = int(number + 0.5) if number >= 0 else int(number)
    if seconds != number:
        warnings.append(RowIssue(row, episode_id, "duration_rounded", f"{raw} -> {seconds}"))
    if not 0 < seconds <= MAX_DURATION_SECONDS:
        raise _RowError(
            "duration_out_of_range",
            f"{raw} is outside 1..{MAX_DURATION_SECONDS} seconds",
        )
    return seconds, warnings


def parse_operator_name(raw: str, row: int, episode_id: str) -> tuple[str | None, list[RowIssue]]:
    value = " ".join(raw.split())
    if not value:
        return None, [RowIssue(row, episode_id, "missing_operator_name", "stored as NULL")]
    return value, []


def parse_quality(raw: str) -> Quality:
    value = raw.strip().lower()
    if not value:
        raise _RowError("missing_quality", "quality is blank")
    try:
        return Quality(value)
    except ValueError:
        raise _RowError(
            "invalid_quality", f"'{raw}' is not one of good/usable/bad"
        ) from None


# --- parsing --------------------------------------------------------------------------


def _parse_row(
    cells: dict[str, str], row: int, known_robots: set[str], now: datetime
) -> ParsedEpisode:
    episode_id = parse_episode_id(cells["episode_id"])
    try:
        robot_id = parse_robot_id(cells["robot_id"], known_robots)
        task_name = parse_task_name(cells["task_name"])
        recorded_at = parse_recorded_at(cells["recorded_at"], now)
        quality = parse_quality(cells["quality"])
        duration, w1 = parse_duration(cells["duration_seconds"], row, episode_id)
        operator, w2 = parse_operator_name(cells["operator_name"], row, episode_id)
    except _RowError as err:
        err.episode_id = episode_id
        raise
    return ParsedEpisode(
        row=row,
        episode_id=episode_id,
        robot_id=robot_id,
        task_name=task_name,
        recorded_at=recorded_at,
        duration_seconds=duration,
        operator_name=operator,
        quality=quality,
        warnings=w1 + w2,
    )


def _resolve_duplicates(
    parsed: list[ParsedEpisode],
) -> tuple[list[ParsedEpisode], list[RowIssue]]:
    by_id: dict[str, list[ParsedEpisode]] = {}
    for episode in parsed:
        by_id.setdefault(episode.episode_id, []).append(episode)

    kept: list[ParsedEpisode] = []
    skipped: list[RowIssue] = []
    for episode_id, group in by_id.items():
        first = group[0]
        if len(group) == 1:
            kept.append(first)
        elif all(e.values() == first.values() for e in group[1:]):
            kept.append(first)
            skipped += [
                RowIssue(e.row, episode_id, "duplicate_in_file", f"identical to row {first.row}")
                for e in group[1:]
            ]
        else:
            rows = ", ".join(str(e.row) for e in group)
            skipped += [
                RowIssue(
                    e.row,
                    episode_id,
                    "conflicting_duplicate",
                    f"episode_id appears in rows {rows} with different values; "
                    "none imported, needs manual review",
                )
                for e in group
            ]
    kept.sort(key=lambda e: e.row)
    return kept, skipped


def parse_csv(text: str, known_robots: set[str], now: datetime | None = None) -> ParseResult:
    now = now or datetime.now(UTC)
    reader = csv.reader(io.StringIO(text, newline=""))
    header = next(reader, None)
    if header is None:
        raise InvalidInput("The file is empty")
    header = [h.strip().lower() for h in header]
    missing_cols = [c for c in COLUMNS if c not in header]
    if missing_cols:
        raise InvalidInput(
            "The CSV header is missing required columns", details={"missing": missing_cols}
        )
    index = {name: header.index(name) for name in COLUMNS}

    parsed: list[ParsedEpisode] = []
    skipped: list[RowIssue] = []
    total = 0
    for row_number, cells in enumerate(reader, start=2):
        total += 1
        if not any(c.strip() for c in cells):
            skipped.append(RowIssue(row_number, None, "blank_row", "row is empty"))
            continue
        if len(cells) != len(header):
            guess = cells[0].strip().upper() if cells else None
            skipped.append(
                RowIssue(
                    row_number,
                    guess or None,
                    "malformed_row",
                    f"expected {len(header)} columns, got {len(cells)}",
                )
            )
            continue
        try:
            parsed.append(
                _parse_row(
                    {name: cells[i] for name, i in index.items()}, row_number, known_robots, now
                )
            )
        except _RowError as err:
            skipped.append(RowIssue(row_number, err.episode_id, err.reason, err.detail))

    kept, duplicate_issues = _resolve_duplicates(parsed)
    skipped = sorted(skipped + duplicate_issues, key=lambda i: i.row)
    return ParseResult(total_rows=total, episodes=kept, skipped=skipped)


# --- database write -------------------------------------------------------------------


def _chunks(items: list[ParsedEpisode], size: int) -> Iterator[list[ParsedEpisode]]:
    for i in range(0, len(items), size):
        yield items[i : i + size]


def _upsert(db: Session, batch: Iterable[ParsedEpisode]) -> tuple[int, list[str]]:
    """Insert new episodes; update existing ones only if a value actually changed.

    ``RETURNING (xmax = 0)`` is the Postgres idiom to tell inserted rows (xmax 0) from
    updated ones. Rows filtered out by the WHERE clause (unchanged) aren't returned.
    """
    rows = [{c: getattr(e, c) for c in COLUMNS} for e in batch]
    stmt = pg_insert(Episode).values(rows)
    table = Episode.__table__
    stmt = stmt.on_conflict_do_update(
        index_elements=[table.c.episode_id],
        set_={**{c: stmt.excluded[c] for c in UPDATABLE}, "updated_at": func.now()},
        where=tuple_(*[table.c[c] for c in UPDATABLE]).is_distinct_from(
            tuple_(*[stmt.excluded[c] for c in UPDATABLE])
        ),
    ).returning(table.c.episode_id, literal_column("(episodes.xmax = 0)").label("inserted"))
    inserted = 0
    updated: list[str] = []
    for episode_id, was_inserted in db.execute(stmt):
        if was_inserted:
            inserted += 1
        else:
            updated.append(episode_id)
    return inserted, updated


def decode_upload(data: bytes) -> str:
    try:
        return data.decode("utf-8-sig")  # tolerate a BOM from Excel exports
    except UnicodeDecodeError:
        raise InvalidInput("The file must be UTF-8 encoded CSV") from None


def import_episodes(
    db: Session, text: str, *, filename: str, uploaded_by: int | None
) -> dict:
    known_robots = set(db.scalars(select(Robot.robot_id)))
    result = parse_csv(text, known_robots)

    inserted = 0
    updated_ids: list[str] = []
    for batch in _chunks(result.episodes, CHUNK_SIZE):
        n, ids = _upsert(db, batch)
        inserted += n
        updated_ids += ids

    warnings = [asdict(w) for w in result.warnings]
    if updated_ids:
        # A correction that downgrades an already-assigned episode needs a human.
        for episode_id, request_id in db.execute(
            select(Assignment.episode_id, Assignment.request_id)
            .join(Episode, Episode.episode_id == Assignment.episode_id)
            .where(
                Assignment.episode_id.in_(updated_ids),
                Assignment.released_at.is_(None),
                Episode.quality == Quality.BAD,
            )
        ):
            warnings.append(
                asdict(
                    RowIssue(
                        0,
                        episode_id,
                        "assigned_episode_now_bad",
                        f"re-graded 'bad' while assigned to request {request_id}",
                    )
                )
            )

    valid = len(result.episodes)
    report = {
        "filename": filename,
        "total_rows": result.total_rows,
        "valid_rows": valid,
        "inserted": inserted,
        "updated": len(updated_ids),
        "unchanged": valid - inserted - len(updated_ids),
        "skipped": len(result.skipped),
        "skipped_by_reason": dict(Counter(i.reason for i in result.skipped).most_common()),
        "skipped_rows": [asdict(i) for i in result.skipped],
        "warnings": warnings,
        "updated_episode_ids": updated_ids,
    }
    run = ImportRun(
        filename=filename[:255],
        sha256=hashlib.sha256(text.encode()).hexdigest(),
        uploaded_by=uploaded_by,
        total_rows=report["total_rows"],
        inserted=report["inserted"],
        updated=report["updated"],
        unchanged=report["unchanged"],
        skipped=report["skipped"],
        report=report,
    )
    db.add(run)
    db.commit()  # the whole import is one transaction: all of it lands, or none of it
    return {"import_id": run.id, **report}
