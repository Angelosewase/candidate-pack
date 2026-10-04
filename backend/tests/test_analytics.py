"""Analytics aggregation tests (service layer).

Tests the in-DB aggregation logic used for the analytics dashboard.
"""

from datetime import UTC, date, datetime, timedelta

from app.models import Episode, Quality, RequestStatus, Role
from app.services import analytics as analytics_service
from app.services import assignments as assign_service
from app.services import requests as request_service
from tests.factories import (
    fully_assign_and_deliver,
    make_episode,
    make_request,
    make_user,
    move_to_in_progress,
)


def _d(day_offset: int = 0) -> date:
    return (datetime.now(UTC) + timedelta(days=day_offset)).date()


class TestAnalyticsEpisodesPerDay:
    def test_episodes_grouped_by_day_and_robot(self, db):
        # 2 episodes on arm-01 today
        make_episode(db, robot_id="arm-01", recorded_at=datetime.now(UTC))
        make_episode(db, robot_id="arm-01", recorded_at=datetime.now(UTC))
        # 1 episode on mobile-01 today
        make_episode(db, robot_id="mobile-01", recorded_at=datetime.now(UTC))
        # 1 episode on arm-01 yesterday
        make_episode(db, robot_id="arm-01", recorded_at=datetime.now(UTC) - timedelta(days=1))
        # 1 episode out of range
        make_episode(db, robot_id="arm-01", recorded_at=datetime.now(UTC) - timedelta(days=5))

        out = analytics_service.get_analytics(db, _d(-1), _d(0))

        epd = out.episodes_per_day
        # We expect 3 groups (yesterday arm-01, today arm-01, today mobile-01)
        assert len(epd) == 3

        yesterday = _d(-1)
        today = _d(0)

        # Note: the results are sorted by day then robot_id
        assert epd[0].day == yesterday
        assert epd[0].robot_id == "arm-01"
        assert epd[0].episodes == 1

        assert epd[1].day == today
        assert epd[1].robot_id == "arm-01"
        assert epd[1].episodes == 2

        assert epd[2].day == today
        assert epd[2].robot_id == "mobile-01"
        assert epd[2].episodes == 1


class TestAnalyticsRequestFulfilment:
    def test_requests_by_status(self, db):
        client = make_user(db, Role.CLIENT)
        staff = make_user(db, Role.OPERATOR)

        # 1 submitted
        make_request(db, client)
        
        # 2 in progress
        r1 = make_request(db, client)
        move_to_in_progress(db, staff, r1)
        r2 = make_request(db, client)
        move_to_in_progress(db, staff, r2)
        
        # 1 delivered
        r3 = make_request(db, client, 1)
        move_to_in_progress(db, staff, r3)
        fully_assign_and_deliver(db, staff, client, r3, 1)

        out = analytics_service.get_analytics(db, _d(-1), _d(1))

        f = out.request_fulfilment
        assert f.total == 4
        assert f.by_status[RequestStatus.SUBMITTED] == 1
        assert f.by_status[RequestStatus.IN_PROGRESS] == 2
        assert f.by_status[RequestStatus.DELIVERED] == 1
        assert f.by_status[RequestStatus.ACCEPTED] == 0
        assert f.by_status[RequestStatus.REJECTED] == 0

    def test_median_time_to_delivery_null_when_none_delivered(self, db):
        client = make_user(db, Role.CLIENT)
        make_request(db, client)  # submitted only

        out = analytics_service.get_analytics(db, _d(-1), _d(1))
        
        f = out.request_fulfilment
        assert f.delivered_count == 0
        assert f.median_hours_submitted_to_delivered is None

    def test_median_time_to_delivery_calculation(self, db):
        from sqlalchemy import update as sa_update
        from app.models import DatasetRequest, RequestStatusEvent

        client = make_user(db, Role.CLIENT)
        staff = make_user(db, Role.OPERATOR)
        now = datetime.now(UTC)

        # We will create two delivered requests and manipulate their timestamps
        # so one took 2 hours, the other 4 hours. Median = 3.

        # Request 1: 2 hours to delivery
        r1 = make_request(db, client, 1)
        move_to_in_progress(db, staff, r1)
        fully_assign_and_deliver(db, staff, client, r1, 1)

        db.execute(
            sa_update(DatasetRequest).where(DatasetRequest.id == r1).values(created_at=now - timedelta(hours=2))
        )
        db.execute(
            sa_update(RequestStatusEvent)
            .where((RequestStatusEvent.request_id == r1) & (RequestStatusEvent.to_status == RequestStatus.DELIVERED))
            .values(created_at=now)
        )

        # Request 2: 4 hours to delivery
        r2 = make_request(db, client, 1)
        move_to_in_progress(db, staff, r2)
        fully_assign_and_deliver(db, staff, client, r2, 1)
        
        db.execute(
            sa_update(DatasetRequest).where(DatasetRequest.id == r2).values(created_at=now - timedelta(hours=4))
        )
        db.execute(
            sa_update(RequestStatusEvent)
            .where((RequestStatusEvent.request_id == r2) & (RequestStatusEvent.to_status == RequestStatus.DELIVERED))
            .values(created_at=now)
        )
        
        db.commit()

        out = analytics_service.get_analytics(db, _d(-1), _d(1))

        f = out.request_fulfilment
        assert f.delivered_count == 2
        # median of 2 and 4 is 3
        assert f.median_hours_submitted_to_delivered == 3.0


class TestAnalyticsTopTasks:
    def test_top_tasks_by_good_episodes_ordered_and_limited(self, db):
        # We need task A (3 good), task B (2 good), task C (1 good), task D (0 good, 2 usable)
        
        # A
        for _ in range(3):
            make_episode(db, Quality.GOOD, task_name="task a", recorded_at=datetime.now(UTC))
        # B
        for _ in range(2):
            make_episode(db, Quality.GOOD, task_name="task b", recorded_at=datetime.now(UTC))
        # C
        for _ in range(1):
            make_episode(db, Quality.GOOD, task_name="task c", recorded_at=datetime.now(UTC))
        # D
        for _ in range(2):
            make_episode(db, Quality.USABLE, task_name="task d", recorded_at=datetime.now(UTC))

        out = analytics_service.get_analytics(db, _d(-1), _d(1))
        top = out.top_tasks_by_good_episodes

        assert len(top) == 3
        
        assert top[0].task_name == "task a"
        assert top[0].good_episodes == 3
        
        assert top[1].task_name == "task b"
        assert top[1].good_episodes == 2
        
        assert top[2].task_name == "task c"
        assert top[2].good_episodes == 1
