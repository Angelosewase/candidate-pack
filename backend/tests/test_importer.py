import pytest
from datetime import datetime, UTC
from app.services.importer import parse_csv

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
