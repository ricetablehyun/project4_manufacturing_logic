"""Earliest feasible slot search across Calendar and Resource constraints."""

from dataclasses import dataclass
from datetime import datetime

from production_control.core.calendar_engine import WorkCalendar, WorkSegment
from production_control.core.resource_engine import (
    Resource,
    ResourceAllocation,
    can_allocate,
)


@dataclass(frozen=True, slots=True)
class ResourceRequirement:
    """Quantity of one Resource required by an operation."""

    resource_code: str
    quantity: int = 1

    def __post_init__(self) -> None:
        if not self.resource_code:
            raise ValueError("resource_code must not be empty")
        if self.quantity <= 0:
            raise ValueError("resource requirement quantity must be greater than 0")


@dataclass(frozen=True, slots=True)
class FeasibleSlot:
    """Calendar-aware slot selected for one operation."""

    start: datetime
    end: datetime
    segments: tuple[WorkSegment, ...]


def _all_segments_feasible(
    *,
    segments: tuple[WorkSegment, ...],
    requirements: tuple[ResourceRequirement, ...],
    resources: dict[str, Resource],
    allocations: list[ResourceAllocation],
) -> bool:
    for requirement in requirements:
        resource = resources.get(requirement.resource_code)
        if resource is None:
            raise ValueError(f"unknown resource: {requirement.resource_code}")
        if requirement.quantity > resource.capacity:
            raise ValueError(
                f"required quantity exceeds capacity for {requirement.resource_code}"
            )

        for segment in segments:
            if not can_allocate(
                resource=resource,
                start=segment.start,
                end=segment.end,
                required_quantity=requirement.quantity,
                existing_allocations=allocations,
            ):
                return False

    return True


def _next_conflict_end(
    *,
    segments: tuple[WorkSegment, ...],
    requirements: tuple[ResourceRequirement, ...],
    allocations: list[ResourceAllocation],
) -> datetime | None:
    required_codes = {requirement.resource_code for requirement in requirements}
    ends: list[datetime] = []

    for allocation in allocations:
        if allocation.resource_code not in required_codes:
            continue

        for segment in segments:
            if max(segment.start, allocation.start) < min(segment.end, allocation.end):
                ends.append(allocation.end)
                break

    return min(ends) if ends else None


def find_earliest_feasible_slot(
    *,
    earliest_start: datetime,
    duration_minutes: float,
    requirements: tuple[ResourceRequirement, ...],
    resources: dict[str, Resource],
    allocations: list[ResourceAllocation],
    calendar: WorkCalendar,
    max_iterations: int = 10_000,
) -> FeasibleSlot:
    """Find the earliest calendar-valid slot satisfying all required resources.

    V1 operations may pause only at work-calendar boundaries. A candidate that
    would conflict with an existing allocation in any working segment is shifted
    forward and recalculated from its new start.
    """

    if duration_minutes <= 0:
        raise ValueError("duration_minutes must be greater than 0")
    if not requirements:
        raise ValueError("at least one resource requirement is required")
    if max_iterations <= 0:
        raise ValueError("max_iterations must be greater than 0")

    candidate = calendar.next_work_start(earliest_start)

    for _ in range(max_iterations):
        segments = calendar.working_segments(candidate, duration_minutes)

        if _all_segments_feasible(
            segments=segments,
            requirements=requirements,
            resources=resources,
            allocations=allocations,
        ):
            return FeasibleSlot(
                start=segments[0].start,
                end=segments[-1].end,
                segments=segments,
            )

        conflict_end = _next_conflict_end(
            segments=segments,
            requirements=requirements,
            allocations=allocations,
        )
        if conflict_end is None:
            raise RuntimeError("resource infeasibility found without a conflicting allocation")

        candidate = calendar.next_work_start(conflict_end)

    raise RuntimeError("could not find a feasible slot within max_iterations")
