"""CSV import unit and integration tests.

Unit tests use ``parse_csv`` (no DB) to verify row-level rules.
Integration tests use ``import_episodes`` (with DB) to verify idempotency
and the upsert behaviour.
"""

import uuid

import pytest

from app.models import Episode, Robot
from app.services.importer import import_episodes, parse_csv


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_HEADER = "episode_id,robot_id,task_name,recorded_at,duration_seconds,operator_name,quality\n"

KNOWN_ROBOTS = {"arm-01"}


def _csv(*rows: str) -> str:
    return _HEADER + "\n".join(rows) + "\n"


def _row(
    episode_id: str = "EP-123",
    robot_id: str = "arm-01",
    task_name: str = "pick cup",
    recorded_at: str = "2026-08-16T23:28:00",
    duration_seconds: str = "78",
    operator_name: str = "Diane",
    quality: str = "good",
) -> str:
    return f"{episode_id},{robot_id},{task_name},{recorded_at},{duration_seconds},{operator_name},{quality}"


def _fresh_id() -> str:
    return f"EP-{uuid.uuid4().int % 10**9:09d}"


# ---------------------------------------------------------------------------
# parse_csv — unit tests (no DB)
# ---------------------------------------------------------------------------


class TestParseCsvValid:
    def test_single_valid_row_is_parsed(self):
        result = parse_csv(_csv(_row()), KNOWN_ROBOTS)
        assert len(result.episodes) == 1
        assert not result.skipped
        ep = result.episodes[0]
        assert ep.episode_id == "EP-123"
        assert ep.task_name == "pick cup"
        assert ep.duration_seconds == 78

    def test_quality_values_are_accepted(self):
        for quality in ("good", "usable", "bad"):
            result = parse_csv(_csv(_row(quality=quality)), KNOWN_ROBOTS)
            assert len(result.episodes) == 1, quality

    def test_missing_duration_stored_as_null(self):
        result = parse_csv(_csv(_row(duration_seconds="n/a")), KNOWN_ROBOTS)
        assert len(result.episodes) == 1
        assert result.episodes[0].duration_seconds is None

    def test_missing_operator_stored_as_null(self):
        result = parse_csv(_csv(_row(operator_name="")), KNOWN_ROBOTS)
        assert len(result.episodes) == 1
        assert result.episodes[0].operator_name is None

    def test_fractional_duration_is_rounded(self):
        result = parse_csv(_csv(_row(duration_seconds="5.7")), KNOWN_ROBOTS)
        assert result.episodes[0].duration_seconds == 6

    def test_episode_id_is_uppercased(self):
        result = parse_csv(_csv(_row(episode_id="ep-001")), KNOWN_ROBOTS)
        assert result.episodes[0].episode_id == "EP-001"

    def test_task_name_normalised_to_lowercase(self):
        result = parse_csv(_csv(_row(task_name="  PICK  CUP  ")), KNOWN_ROBOTS)
        assert result.episodes[0].task_name == "pick cup"


class TestParseCsvInvalidRows:
    def test_invalid_episode_id_format_is_skipped(self):
        result = parse_csv(_csv(_row(episode_id="INVALID")), KNOWN_ROBOTS)
        assert len(result.episodes) == 0
        assert result.skipped[0].reason == "invalid_episode_id"

    def test_missing_episode_id_is_skipped(self):
        result = parse_csv(_csv(_row(episode_id="")), KNOWN_ROBOTS)
        assert result.skipped[0].reason == "missing_episode_id"

    def test_unknown_robot_is_skipped(self):
        result = parse_csv(_csv(_row(robot_id="arm-99")), KNOWN_ROBOTS)
        assert result.skipped[0].reason == "unknown_robot"

    def test_duration_out_of_range_is_skipped(self):
        result = parse_csv(_csv(_row(duration_seconds="99999")), KNOWN_ROBOTS)
        assert result.skipped[0].reason == "duration_out_of_range"

    def test_invalid_quality_is_skipped(self):
        result = parse_csv(_csv(_row(quality="superb")), KNOWN_ROBOTS)
        assert result.skipped[0].reason == "invalid_quality"

    def test_blank_row_is_skipped(self):
        result = parse_csv(_HEADER + ",,,,,,\n", KNOWN_ROBOTS)
        assert result.skipped[0].reason == "blank_row"

    def test_missing_required_column_raises(self):
        from app.errors import InvalidInput

        with pytest.raises(InvalidInput, match="missing required columns"):
            parse_csv("episode_id,robot_id\nEP-001,arm-01\n", KNOWN_ROBOTS)

    def test_future_recorded_at_is_skipped(self):
        result = parse_csv(_csv(_row(recorded_at="2099-01-01T00:00:00")), KNOWN_ROBOTS)
        assert result.skipped[0].reason == "future_recorded_at"


class TestParseCsvDuplicates:
    def test_identical_duplicate_rows_import_once(self):
        row = _row(episode_id="EP-111")
        result = parse_csv(_csv(row, row), KNOWN_ROBOTS)
        assert len(result.episodes) == 1
        assert result.episodes[0].episode_id == "EP-111"
        assert any(s.reason == "duplicate_in_file" for s in result.skipped)

    def test_conflicting_duplicate_rows_skip_all(self):
        row_good = _row(episode_id="EP-222", quality="good")
        row_bad = _row(episode_id="EP-222", quality="bad")
        result = parse_csv(_csv(row_good, row_bad), KNOWN_ROBOTS)
        assert len(result.episodes) == 0
        reasons = [s.reason for s in result.skipped]
        assert reasons.count("conflicting_duplicate") == 2


# ---------------------------------------------------------------------------
# import_episodes — integration tests (with DB)
# ---------------------------------------------------------------------------


def _ensure_robot(db, robot_id: str = "arm-01") -> None:
    if db.get(Robot, robot_id) is None:
        db.add(Robot(robot_id=robot_id))
        db.commit()


class TestImportEpisodesIdempotency:
    def test_first_run_inserts_episode(self, db):
        _ensure_robot(db)
        episode_id = _fresh_id()
        report = import_episodes(
            db, _csv(_row(episode_id=episode_id)), filename="a.csv", uploaded_by=None
        )
        assert report["inserted"] == 1
        assert report["updated"] == 0
        assert report["unchanged"] == 0

    def test_second_run_is_unchanged(self, db):
        _ensure_robot(db)
        episode_id = _fresh_id()
        text = _csv(_row(episode_id=episode_id))
        import_episodes(db, text, filename="a.csv", uploaded_by=None)
        report = import_episodes(db, text, filename="a.csv", uploaded_by=None)
        assert report["inserted"] == 0
        assert report["updated"] == 0
        assert report["unchanged"] == 1

    def test_corrected_quality_updates_existing(self, db):
        _ensure_robot(db)
        episode_id = _fresh_id()
        import_episodes(
            db, _csv(_row(episode_id=episode_id, quality="good")), filename="a.csv", uploaded_by=None
        )
        report = import_episodes(
            db, _csv(_row(episode_id=episode_id, quality="usable")), filename="a.csv", uploaded_by=None
        )
        assert report["updated"] == 1
        assert report["updated_episode_ids"] == [episode_id]
        assert db.get(Episode, episode_id).quality.value == "usable"

    def test_multiple_episodes_idempotent(self, db):
        _ensure_robot(db)
        ids = [_fresh_id() for _ in range(5)]
        rows = [_row(episode_id=eid) for eid in ids]
        text = _csv(*rows)
        first = import_episodes(db, text, filename="bulk.csv", uploaded_by=None)
        assert first["inserted"] == 5

        second = import_episodes(db, text, filename="bulk.csv", uploaded_by=None)
        assert second["inserted"] == 0
        assert second["unchanged"] == 5

    def test_import_run_is_recorded(self, db):
        from sqlalchemy import select
        from app.models import ImportRun

        _ensure_robot(db)
        episode_id = _fresh_id()
        report = import_episodes(
            db, _csv(_row(episode_id=episode_id)), filename="recorded.csv", uploaded_by=None
        )
        run = db.get(ImportRun, report["import_id"])
        assert run is not None
        assert run.filename == "recorded.csv"
        assert run.inserted == 1
