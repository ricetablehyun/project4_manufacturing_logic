"""Resource-capacity checks for finite scheduling."""

from dataclasses import dataclass
from datetime import datetime


@dataclass(frozen=True, slots=True)
class Resource:
    code: str
    capacity: int

    def __post_init__(self) -> None:
        if not self.code:
            raise ValueError("resource code must not be empty")
        if self.capacity <= 0:
            raise ValueError("resource capacity must be greater than 0")


@dataclass(frozen=True, slots=True)
class ResourceAllocation:
    resource_code: str
    start: datetime
    end: datetime
    quantity: int = 1

    def __post_init__(self) -> None:
        if self.start >= self.end:
            raise ValueError("allocation start must be earlier than end")
        if self.quantity <= 0:
            raise ValueError("allocation quantity must be greater than 0")


def can_allocate(
    *,
    resource: Resource,
    start: datetime,
    end: datetime,
    required_quantity: int,
    existing_allocations: list[ResourceAllocation],
) -> bool:
    """Return whether requested capacity is available for the whole interval."""

    if start >= end:
        raise ValueError("start must be earlier than end")
    if required_quantity <= 0:
        raise ValueError("required_quantity must be greater than 0")
    if required_quantity > resource.capacity:
        return False

    events: list[tuple[datetime, int]] = []
    for allocation in existing_allocations:
        if allocation.resource_code != resource.code:
            continue

        overlap_start = max(start, allocation.start)
        overlap_end = min(end, allocation.end)
        if overlap_start >= overlap_end:
            continue

        events.append((overlap_start, allocation.quantity))
        events.append((overlap_end, -allocation.quantity))

    # At the same timestamp, release capacity before allocating new overlap.
    events.sort(key=lambda item: (item[0], item[1]))

    used = 0
    for _, delta in events:
        used += delta
        if used + required_quantity > resource.capacity:
            return False

    return True
