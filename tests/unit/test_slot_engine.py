from datetime import datetime
from zoneinfo import ZoneInfo

from production_control.core.calendar_engine import WorkCalendar
from production_control.core.resource_engine import Resource, ResourceAllocation
from production_control.core.slot_engine import ResourceRequirement, find_earliest_feasible_slot

SEOUL = ZoneInfo("Asia/Seoul")


def dt(day: int, hour: int, minute: int = 0) -> datetime:
    return datetime(2026, 10, day, hour, minute, tzinfo=SEOUL)


def resources() -> dict[str, Resource]:
    return {
        "WORKER_POOL": Resource("WORKER_POOL", capacity=2),
        "TUNING_STATION": Resource("TUNING_STATION", capacity=1),
        "TEST_STATION": Resource("TEST_STATION", capacity=1),
    }


def tuning_requirements() -> tuple[ResourceRequirement, ...]:
    return (
        ResourceRequirement("WORKER_POOL", 1),
        ResourceRequirement("TUNING_STATION", 1),
    )


def test_empty_schedule_uses_earliest_start() -> None:
    slot = find_earliest_feasible_slot(
        earliest_start=dt(5, 9),
        duration_minutes=25,
        requirements=tuning_requirements(),
        resources=resources(),
        allocations=[],
        calendar=WorkCalendar(),
    )

    assert slot.start == dt(5, 9)
    assert slot.end == dt(5, 9, 25)


def test_tuning_station_conflict_delays_operation() -> None:
    slot = find_earliest_feasible_slot(
        earliest_start=dt(5, 9),
        duration_minutes=25,
        requirements=tuning_requirements(),
        resources=resources(),
        allocations=[
            ResourceAllocation("TUNING_STATION", dt(5, 9), dt(5, 9, 30)),
        ],
        calendar=WorkCalendar(),
    )

    assert slot.start == dt(5, 9, 30)
    assert slot.end == dt(5, 9, 55)


def test_worker_pool_capacity_two_allows_operation_with_one_worker_busy() -> None:
    slot = find_earliest_feasible_slot(
        earliest_start=dt(5, 9),
        duration_minutes=25,
        requirements=tuning_requirements(),
        resources=resources(),
        allocations=[
            ResourceAllocation("WORKER_POOL", dt(5, 9), dt(5, 10)),
        ],
        calendar=WorkCalendar(),
    )

    assert slot.start == dt(5, 9)


def test_worker_pool_full_delays_until_one_worker_is_released() -> None:
    slot = find_earliest_feasible_slot(
        earliest_start=dt(5, 9),
        duration_minutes=25,
        requirements=tuning_requirements(),
        resources=resources(),
        allocations=[
            ResourceAllocation("WORKER_POOL", dt(5, 9), dt(5, 9, 20)),
            ResourceAllocation("WORKER_POOL", dt(5, 9), dt(5, 9, 40)),
        ],
        calendar=WorkCalendar(),
    )

    assert slot.start == dt(5, 9, 20)
    assert slot.end == dt(5, 9, 45)


def test_multiple_required_resources_use_latest_relevant_release() -> None:
    slot = find_earliest_feasible_slot(
        earliest_start=dt(5, 9),
        duration_minutes=25,
        requirements=tuning_requirements(),
        resources=resources(),
        allocations=[
            ResourceAllocation("WORKER_POOL", dt(5, 9), dt(5, 9, 20), quantity=2),
            ResourceAllocation("TUNING_STATION", dt(5, 9), dt(5, 9, 30)),
        ],
        calendar=WorkCalendar(),
    )

    assert slot.start == dt(5, 9, 30)


def test_operation_can_span_calendar_boundary() -> None:
    slot = find_earliest_feasible_slot(
        earliest_start=dt(5, 16, 50),
        duration_minutes=25,
        requirements=tuning_requirements(),
        resources=resources(),
        allocations=[],
        calendar=WorkCalendar(),
    )

    assert slot.start == dt(5, 16, 50)
    assert slot.end == dt(6, 9, 15)
    assert len(slot.segments) == 2


def test_future_segment_conflict_shifts_whole_candidate_forward() -> None:
    slot = find_earliest_feasible_slot(
        earliest_start=dt(5, 16, 50),
        duration_minutes=25,
        requirements=tuning_requirements(),
        resources=resources(),
        allocations=[
            ResourceAllocation("TUNING_STATION", dt(6, 9), dt(6, 9, 10)),
        ],
        calendar=WorkCalendar(),
    )

    assert slot.start == dt(6, 9, 10)
    assert slot.end == dt(6, 9, 35)
