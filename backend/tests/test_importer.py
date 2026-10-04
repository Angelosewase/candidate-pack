import pytest
import uuid
from datetime import datetime, UTC
from app.models import Episode, Robot
from app.services.importer import import_episodes, parse_csv


def _csv(episode_id: str, quality: str = "good") -> str:
    return f"""episode_id,robot_id,task_name,recorded_at,duration_seconds,operator_name,quality
{episode_id},arm-01,pick cup,2026-08-16T23:28:00,78,Diane,{quality}
"""

def test_importer_valid_parsing():
    csv_data = """episode_id,robot_id,task_name,recorded_at,duration_seconds,operator_name,quality
EP-123,arm-01,pick cup,2026-08-16T23:28:00,78,Diane,good
"""
    result = parse_csv(csv_data, {"arm-01"})
    assert len(result.episodes) == 1
    assert not result.skipped
    
    ep = result.episodes[0]
    assert ep.episode_id == "EP-123"
    assert ep.task_name == "pick cup"
    assert ep.duration_seconds == 78

def test_importer_invalid_rows_skipped():
    # EP-ABC is invalid ID, duration 4000 > max, unknown robot
    csv_data = """episode_id,robot_id,task_name,recorded_at,duration_seconds,operator_name,quality
EP-ABC,arm-01,pick cup,2026-08-16T23:28:00,78,Diane,good
EP-124,arm-99,pick cup,2026-08-16T23:28:00,78,Diane,good
EP-125,arm-01,pick cup,2026-08-16T23:28:00,4000,Diane,good
"""
    result = parse_csv(csv_data, {"arm-01"})
    assert len(result.episodes) == 0
    assert len(result.skipped) == 3
    assert result.skipped[0].reason == "invalid_episode_id"
    assert result.skipped[1].reason == "unknown_robot"
    assert result.skipped[2].reason == "duration_out_of_range"

def test_importer_duplicates_in_file():
    # First and second rows are identical, third row has different quality.
    # The identical duplicate should be ignored, the conflicting one should cause both to be skipped.
    csv_data = """episode_id,robot_id,task_name,recorded_at,duration_seconds,operator_name,quality
EP-111,arm-01,pick cup,2026-08-16T23:28:00,78,Diane,good
EP-111,arm-01,pick cup,2026-08-16T23:28:00,78,Diane,good
EP-222,arm-01,pick cup,2026-08-16T23:28:00,78,Diane,good
EP-222,arm-01,pick cup,2026-08-16T23:28:00,78,Diane,bad
"""
    result = parse_csv(csv_data, {"arm-01"})
    assert len(result.episodes) == 1
    assert result.episodes[0].episode_id == "EP-111"
    
    # 1 identical dup skipped, 2 conflicting dups skipped
    assert len(result.skipped) == 3
    reasons = [s.reason for s in result.skipped]
    assert "duplicate_in_file" in reasons
    assert reasons.count("conflicting_duplicate") == 2


def test_import_idempotent_second_run_changes_nothing(db):
    if db.get(Robot, "arm-01") is None:
        db.add(Robot(robot_id="arm-01"))
        db.commit()
    episode_id = f"EP-{uuid.uuid4().int % 10**9:09d}"
    text = _csv(episode_id)
    first = import_episodes(db, text, filename="a.csv", uploaded_by=None)
    assert first["inserted"] == 1
    assert first["unchanged"] == 0
    second = import_episodes(db, text, filename="a.csv", uploaded_by=None)
    assert second["inserted"] == 0
    assert second["updated"] == 0
    assert second["unchanged"] == 1
    assert second["skipped"] == 0


def test_import_correction_updates_existing_row(db):
    if db.get(Robot, "arm-01") is None:
        db.add(Robot(robot_id="arm-01"))
        db.commit()
    episode_id = f"EP-{uuid.uuid4().int % 10**9:09d}"
    import_episodes(db, _csv(episode_id, "good"), filename="a.csv", uploaded_by=None)
    report = import_episodes(db, _csv(episode_id, "usable"), filename="a.csv", uploaded_by=None)
    assert report["updated"] == 1
    assert report["updated_episode_ids"] == [episode_id]
    assert db.get(Episode, episode_id).quality.value == "usable"
