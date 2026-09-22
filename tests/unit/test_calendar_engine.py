from datetime import datetime
from zoneinfo import ZoneInfo

import pytest

from production_control.core.calendar_engine import WorkCalendar

SEOUL = ZoneInfo("Asia/Seoul")


def dt(year: int, month: int, day: int, hour: int, minute: int = 0) -> datetime:
    return datetime(year, month, day, hour, minute, tzinfo=SEOUL)


def test_friday_working_lead_time_crosses_weekend() -> None:
    calendar = WorkCalendar()

    finish = calendar.add_working_minutes(dt(2026, 10, 9, 16), 120)

    assert finish == dt(2026, 10, 12, 10)


def test_after_close_moves_to_next_workday_opening() -> None:
    calendar = WorkCalendar()

    assert calendar.next_work_start(dt(2026, 10, 5, 18)) == dt(2026, 10, 6, 9)


def test_weekend_moves_to_monday() -> None:
    calendar = WorkCalendar()

    assert calendar.next_work_start(dt(2026, 10, 10, 12)) == dt(2026, 10, 12, 9)


def test_working_minutes_between_counts_only_open_hours() -> None:
    calendar = WorkCalendar()

    minutes = calendar.working_minutes_between(
        dt(2026, 10, 9, 16),
        dt(2026, 10, 12, 10),
    )

    assert minutes == 120


def test_rejects_naive_datetime() -> None:
    calendar = WorkCalendar()

    with pytest.raises(ValueError):
        calendar.add_working_minutes(datetime(2026, 10, 5, 9), 30)


def test_working_segments_split_at_calendar_boundary() -> None:
    calendar = WorkCalendar()

    segments = calendar.working_segments(dt(2026, 10, 5, 16, 50), 25)

    assert len(segments) == 2
    assert segments[0].start == dt(2026, 10, 5, 16, 50)
    assert segments[0].end == dt(2026, 10, 5, 17)
    assert segments[1].start == dt(2026, 10, 6, 9)
    assert segments[1].end == dt(2026, 10, 6, 9, 15)
