from datetime import datetime
from zoneinfo import ZoneInfo

import pytest

from production_control.core.calendar_engine import WorkCalendar
from production_control.core.dynamic_priority import (
    DynamicLotPriorityState,
    build_dynamic_priority_input,
)

SEOUL = ZoneInfo("Asia/Seoul")


def dt(day: int, hour: int, minute: int = 0) -> datetime:
    return datetime(2026, 10, day, hour, minute, tzinfo=SEOUL)


def state(*, deadline: datetime, remaining: float) -> DynamicLotPriorityState:
    return DynamicLotPriorityState(
        lot_id="LOT-01",
        release_at=dt(9, 9),
        deadline=deadline,
        remaining_work_minutes=remaining,
    )


def test_friday_to_monday_counts_only_working_minutes() -> None:
    priority = build_dynamic_priority_input(
        state=state(deadline=dt(12, 10), remaining=120),
        decision_time=dt(9, 16, 30),
        calendar=WorkCalendar(),
    )

    assert priority.time_until_deadline_minutes == 90


def test_slack_uses_working_time_budget() -> None:
    priority = build_dynamic_priority_input(
        state=state(deadline=dt(12, 10), remaining=120),
        decision_time=dt(9, 16, 30),
        calendar=WorkCalendar(),
    )

    assert priority.slack_minutes == -30


def test_cr_uses_working_time_budget() -> None:
    priority = build_dynamic_priority_input(
        state=state(deadline=dt(12, 10), remaining=120),
        decision_time=dt(9, 16, 30),
        calendar=WorkCalendar(),
    )

    assert priority.critical_ratio == pytest.approx(0.75)


def test_past_deadline_returns_negative_working_minutes() -> None:
    priority = build_dynamic_priority_input(
        state=state(deadline=dt(9, 16), remaining=60),
        decision_time=dt(9, 16, 30),
        calendar=WorkCalendar(),
    )

    assert priority.time_until_deadline_minutes == -30
    assert priority.slack_minutes == -90


def test_after_hours_reference_skips_closed_time() -> None:
    priority = build_dynamic_priority_input(
        state=state(deadline=dt(12, 10), remaining=30),
        decision_time=dt(9, 18),
        calendar=WorkCalendar(),
    )

    assert priority.time_until_deadline_minutes == 60


def test_equal_decision_time_and_deadline_has_zero_time_budget() -> None:
    priority = build_dynamic_priority_input(
        state=state(deadline=dt(9, 15), remaining=30),
        decision_time=dt(9, 15),
        calendar=WorkCalendar(),
    )

    assert priority.time_until_deadline_minutes == 0
