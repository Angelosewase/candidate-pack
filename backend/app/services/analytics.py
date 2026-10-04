"""Analytics. Every aggregation runs in Postgres; Python only shapes the result rows.

Plain SQL is used on purpose: these are the queries we'd EXPLAIN when tuning, so it
helps that the code *is* the SQL. Time buckets are UTC days.
"""

from datetime import UTC, date, datetime, time, timedelta

from sqlalchemy import text
from sqlalchemy.orm import Session

from app.models import RequestStatus
from app.schemas import AnalyticsOut, EpisodesPerDay, RequestFulfilment, TopTask

EPISODES_PER_DAY = text("""
    SELECT (recorded_at AT TIME ZONE 'UTC')::date AS day, robot_id, count(*) AS episodes
    FROM episodes
    WHERE recorded_at >= :start AND recorded_at < :end
    GROUP BY day, robot_id
    ORDER BY day, robot_id
""")

REQUESTS_BY_STATUS = text("""
    SELECT status, count(*) AS n
    FROM dataset_requests
    WHERE created_at >= :start AND created_at < :end
    GROUP BY status
""")

# Cohort: requests *submitted* in the range that have been delivered at least once.
# Duration is measured to the FIRST delivery (rework after a rejection doesn't reset
# it). The LATERAL subquery uses ix_events_request_created per request, instead of
# aggregating the whole events table.
MEDIAN_TIME_TO_DELIVERY = text("""
    SELECT count(*) AS delivered,
           percentile_cont(0.5) WITHIN GROUP (
               ORDER BY extract(epoch FROM d.first_delivered_at - r.created_at)
           ) AS median_seconds
    FROM dataset_requests r
    CROSS JOIN LATERAL (
        SELECT min(e.created_at) AS first_delivered_at
        FROM request_status_events e
        WHERE e.request_id = r.id AND e.to_status = 'delivered'
    ) d
    WHERE r.created_at >= :start AND r.created_at < :end
      AND d.first_delivered_at IS NOT NULL
""")

TOP_TASKS_BY_GOOD = text("""
    SELECT task_name, count(*) AS good_episodes
    FROM episodes
    WHERE quality = 'good' AND recorded_at >= :start AND recorded_at < :end
    GROUP BY task_name
    ORDER BY good_episodes DESC, task_name
    LIMIT 5
""")


def get_analytics(db: Session, date_from: date, date_to: date) -> AnalyticsOut:
    """``date_from`` and ``date_to`` are inclusive UTC calendar days."""
    params = {
        "start": datetime.combine(date_from, time.min, tzinfo=UTC),
        "end": datetime.combine(date_to + timedelta(days=1), time.min, tzinfo=UTC),
    }

    per_day = [
        EpisodesPerDay(day=r.day, robot_id=r.robot_id, episodes=r.episodes)
        for r in db.execute(EPISODES_PER_DAY, params)
    ]

    by_status = {s: 0 for s in RequestStatus}
    for r in db.execute(REQUESTS_BY_STATUS, params):
        by_status[RequestStatus(r.status)] = r.n
    median_row = db.execute(MEDIAN_TIME_TO_DELIVERY, params).one()
    fulfilment = RequestFulfilment(
        by_status=by_status,
        total=sum(by_status.values()),
        delivered_count=median_row.delivered,
        median_hours_submitted_to_delivered=(
            round(median_row.median_seconds / 3600, 2)
            if median_row.median_seconds is not None
            else None
        ),
    )

    top = [
        TopTask(task_name=r.task_name, good_episodes=r.good_episodes)
        for r in db.execute(TOP_TASKS_BY_GOOD, params)
    ]

    return AnalyticsOut(
        date_from=date_from,
        date_to=date_to,
        episodes_per_day=per_day,
        request_fulfilment=fulfilment,
        top_tasks_by_good_episodes=top,
    )
