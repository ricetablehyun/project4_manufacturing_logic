from datetime import datetime
from zoneinfo import ZoneInfo

from production_control.core.resource_engine import (
    Resource,
    ResourceAllocation,
    can_allocate,
)


SEOUL = ZoneInfo("Asia/Seoul")


def dt(hour: int, minute: int = 0) -> datetime:
    return datetime(2026, 10, 5, hour, minute, tzinfo=SEOUL)


def test_worker_pool_capacity_two_allows_second_parallel_job() -> None:
    worker_pool = Resource(code="WORKER_POOL", capacity=2)
    allocations = [
        ResourceAllocation("WORKER_POOL", dt(9), dt(10), quantity=1),
    ]

    assert can_allocate(
        resource=worker_pool,
        start=dt(9, 30),
        end=dt(10, 30),
        required_quantity=1,
        existing_allocations=allocations,
    )


def test_worker_pool_capacity_two_rejects_third_parallel_job() -> None:
    worker_pool = Resource(code="WORKER_POOL", capacity=2)
    allocations = [
        ResourceAllocation("WORKER_POOL", dt(9), dt(10), quantity=1),
        ResourceAllocation("WORKER_POOL", dt(9, 15), dt(10, 15), quantity=1),
    ]

    assert not can_allocate(
        resource=worker_pool,
        start=dt(9, 30),
        end=dt(9, 45),
        required_quantity=1,
        existing_allocations=allocations,
    )


def test_capacity_one_machine_rejects_overlap() -> None:
    tuning = Resource(code="TUNING_STATION", capacity=1)
    allocations = [
        ResourceAllocation("TUNING_STATION", dt(9), dt(9, 30)),
    ]

    assert not can_allocate(
        resource=tuning,
        start=dt(9, 15),
        end=dt(9, 45),
        required_quantity=1,
        existing_allocations=allocations,
    )


def test_adjacent_machine_jobs_do_not_overlap() -> None:
    tuning = Resource(code="TUNING_STATION", capacity=1)
    allocations = [
        ResourceAllocation("TUNING_STATION", dt(9), dt(9, 30)),
    ]

    assert can_allocate(
        resource=tuning,
        start=dt(9, 30),
        end=dt(10),
        required_quantity=1,
        existing_allocations=allocations,
    )
