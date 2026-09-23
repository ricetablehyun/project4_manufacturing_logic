from datetime import datetime
from zoneinfo import ZoneInfo

import pytest

from production_control.core.calendar_engine import WorkCalendar
from production_control.core.external_lead_time import (
    LeadTimeBasis,
    LotLeadTimeSpec,
    schedule_lot_lead_time,
)

SEOUL = ZoneInfo("Asia/Seoul")


def dt(day: int, hour: int, minute: int = 0) -> datetime:
    return datetime(2026, 10, day, hour, minute, tzinfo=SEOUL)


def spec(
    *,
    ready_at: datetime,
    lead_minutes: float,
    basis: LeadTimeBasis,
) -> LotLeadTimeSpec:
    return LotLeadTimeSpec(
        lot_id="LOT-A",
        process_code="EXTERNAL_FEED_BONDING",
        ready_at=ready_at,
        lead_minutes=lead_minutes,
        basis=basis,
    )


def test_working_lead_skips_nights_and_weekend() -> None:
    result = schedule_lot_lead_time(
        spec=spec(
            ready_at=dt(9, 16, 30),
            lead_minutes=90,
            basis=LeadTimeBasis.WORKING,
        ),
        calendar=WorkCalendar(),
    )

    assert result.start == dt(9, 16, 30)
    assert result.end == dt(12, 10)


def test_calendar_lead_counts_closed_time() -> None:
    result = schedule_lot_lead_time(
        spec=spec(
            ready_at=dt(9, 16, 30),
            lead_minutes=90,
            basis=LeadTimeBasis.CALENDAR,
        ),
        calendar=WorkCalendar(),
    )

    assert result.start == dt(9, 16, 30)
    assert result.end == dt(9, 18)


def test_working_lead_before_shift_starts_at_calendar_open() -> None:
    result = schedule_lot_lead_time(
        spec=spec(
            ready_at=dt(5, 8),
            lead_minutes=60,
            basis=LeadTimeBasis.WORKING,
        ),
        calendar=WorkCalendar(),
    )

    assert result.start == dt(5, 9)
    assert result.end == dt(5, 10)


def test_calendar_lead_can_cross_weekend_without_shift_logic() -> None:
    result = schedule_lot_lead_time(
        spec=spec(
            ready_at=dt(9, 16),
            lead_minutes=60 * 48,
            basis=LeadTimeBasis.CALENDAR,
        ),
        calendar=WorkCalendar(),
    )

    assert result.end == dt(11, 16)


def test_result_preserves_lot_process_basis_and_duration() -> None:
    result = schedule_lot_lead_time(
        spec=spec(
            ready_at=dt(5, 9),
            lead_minutes=180,
            basis=LeadTimeBasis.WORKING,
        ),
        calendar=WorkCalendar(),
    )

    assert result.lot_id == "LOT-A"
    assert result.process_code == "EXTERNAL_FEED_BONDING"
    assert result.basis is LeadTimeBasis.WORKING
    assert result.lead_minutes == 180


def test_external_lead_does_not_create_resource_allocations() -> None:
    result = schedule_lot_lead_time(
        spec=spec(
            ready_at=dt(5, 9),
            lead_minutes=180,
            basis=LeadTimeBasis.WORKING,
        ),
        calendar=WorkCalendar(),
    )

    assert not hasattr(result, "allocations")


@pytest.mark.parametrize("invalid", [0, -1, float("inf"), float("nan")])
def test_rejects_invalid_lead_minutes(invalid: float) -> None:
    with pytest.raises(ValueError):
        spec(
            ready_at=dt(5, 9),
            lead_minutes=invalid,
            basis=LeadTimeBasis.WORKING,
        )


def test_rejects_naive_ready_at() -> None:
    with pytest.raises(ValueError):
        spec(
            ready_at=datetime(2026, 10, 5, 9),
            lead_minutes=60,
            basis=LeadTimeBasis.WORKING,
        )
