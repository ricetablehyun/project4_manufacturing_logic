from datetime import date, datetime, time, timedelta
from zoneinfo import ZoneInfo

import pytest

from production_control.core.calendar_engine import WorkCalendar
from production_control.core.overtime import overtime_used_by_day, overtime_window_days
from production_control.core.resource_engine import ResourceAllocation

SEOUL = ZoneInfo("Asia/Seoul")
MONDAY = date(2026, 10, 5)


def at(day: int, hour: int, minute: int = 0) -> datetime:
    return datetime(2026, 10, day, hour, minute, tzinfo=SEOUL)


def test_overtime_extends_only_the_chosen_day() -> None:
    calendar = WorkCalendar().with_overtime([MONDAY], time(19, 0))

    assert calendar.is_working_time(at(5, 18, 30))
    assert not calendar.is_working_time(at(6, 18, 30))
    assert calendar.add_working_minutes(at(5, 16, 0), 120) == at(5, 18, 0)
    assert calendar.working_minutes_between(at(5, 9), at(6, 9)) == 600
    assert calendar.closing_time(MONDAY) == at(5, 19)
    assert calendar.regular_close(MONDAY) == at(5, 17)


def test_overtime_rejects_non_working_days_and_early_ends() -> None:
    with pytest.raises(ValueError, match="not a working day"):
        WorkCalendar(overtime=((date(2026, 10, 10), time(19, 0)),))
    with pytest.raises(ValueError, match="end after work_end"):
        WorkCalendar(overtime=((MONDAY, time(16, 0)),))


def test_window_days_are_weekdays_still_ahead_and_not_yet_opened() -> None:
    calendar = WorkCalendar().with_overtime([date(2026, 10, 6)], time(19, 0))

    days = overtime_window_days(calendar, start=at(5, 19, 30), through=date(2026, 10, 12))

    # Monday's window has passed, Tuesday is already open, the weekend is closed.
    assert days == (date(2026, 10, 7), date(2026, 10, 8), date(2026, 10, 9), date(2026, 10, 12))


def test_used_overtime_counts_from_regular_close_to_last_release() -> None:
    calendar = WorkCalendar().with_overtime([MONDAY, date(2026, 10, 6)], time(19, 0))
    allocations = [
        ResourceAllocation(resource_code="WORKER_POOL", start=at(5, 16, 30), end=at(5, 17, 40)),
        ResourceAllocation(resource_code="TEST_STATION", start=at(5, 17, 10), end=at(5, 18, 15)),
        ResourceAllocation(resource_code="WORKER_POOL", start=at(6, 9), end=at(6, 16)),
    ]

    used = overtime_used_by_day(
        calendar=calendar, allocations=allocations, days=[MONDAY, date(2026, 10, 6)]
    )

    assert used == {MONDAY: 75.0}


def test_float_rounding_tail_does_not_spill_into_the_next_day() -> None:
    """A Pace-average duration that exceeds the day's remaining time only by
    float noise must end at the close, not create a zero-length segment."""

    calendar = WorkCalendar()
    start = at(5, 16, 34) + timedelta(seconds=14, microseconds=482759)
    available = (at(5, 17) - start).total_seconds() / 60

    segments = calendar.working_segments(start, available + 1e-9)

    assert [(segment.start, segment.end) for segment in segments] == [(start, at(5, 17))]
    assert calendar.add_working_minutes(start, available + 1e-9) == at(5, 17)
