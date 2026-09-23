"""Finite-capacity scheduling for internal Unit operations.

The scheduler enforces routing precedence, optional initial WIP-buffer release,
the common WorkCalendar, and Resource capacity. It deliberately does not choose
a production priority rule. The caller supplies a dispatch sequence generated
by the planning layer (for example FCFS, EDD, Slack, or CR).
"""

from collections.abc import Iterable
from dataclasses import dataclass
from datetime import datetime

from production_control.core.calendar_engine import WorkCalendar, WorkSegment
from production_control.core.resource_engine import Resource, ResourceAllocation
from production_control.core.slot_engine import (
    ResourceRequirement,
    find_earliest_feasible_slot,
)


@dataclass(frozen=True, slots=True)
class OperationSpec:
    """Scheduling input for one normal-routing Unit operation."""

    operation_id: str
    lot_id: str
    unit_id: str
    step_seq: int
    process_code: str
    duration_minutes: float
    requirements: tuple[ResourceRequirement, ...]
    release_at: datetime
    release_buffer_k: int | None = None
    execution_seq: int | None = None

    def __post_init__(self) -> None:
        if not self.operation_id:
            raise ValueError("operation_id must not be empty")
        if not self.lot_id:
            raise ValueError("lot_id must not be empty")
        if not self.unit_id:
            raise ValueError("unit_id must not be empty")
        if self.step_seq <= 0:
            raise ValueError("step_seq must be greater than 0")
        if not self.process_code:
            raise ValueError("process_code must not be empty")
        if self.duration_minutes <= 0:
            raise ValueError("duration_minutes must be greater than 0")
        if not self.requirements:
            raise ValueError("at least one resource requirement is required")
        if self.release_buffer_k is not None and self.release_buffer_k <= 0:
            raise ValueError("release_buffer_k must be greater than 0 when set")
        if self.execution_seq is not None and self.execution_seq <= 0:
            raise ValueError("execution_seq must be greater than 0 when set")

    @property
    def precedence_seq(self) -> int:
        """Execution-order key; normal routing falls back to RoutingStep sequence."""

        return self.execution_seq if self.execution_seq is not None else self.step_seq


@dataclass(frozen=True, slots=True)
class ScheduledOperation:
    """Finite-capacity result for one Unit operation."""

    operation_id: str
    lot_id: str
    unit_id: str
    step_seq: int
    process_code: str
    start: datetime
    end: datetime
    segments: tuple[WorkSegment, ...]
    execution_seq: int | None = None

    @property
    def precedence_seq(self) -> int:
        return self.execution_seq if self.execution_seq is not None else self.step_seq


@dataclass(frozen=True, slots=True)
class LotProcessForecast:
    """Aggregated internal schedule result at LOT × process resolution."""

    lot_id: str
    process_code: str
    forecast_start: datetime
    forecast_end: datetime
    scheduled_operation_count: int


@dataclass(frozen=True, slots=True)
class ScheduleResult:
    operations: tuple[ScheduledOperation, ...]
    allocations: tuple[ResourceAllocation, ...]


def _validate_inputs(
    operations: tuple[OperationSpec, ...],
    dispatch_sequence: tuple[str, ...],
) -> None:
    operation_ids = [operation.operation_id for operation in operations]
    if len(operation_ids) != len(set(operation_ids)):
        raise ValueError("operation_id values must be unique")

    execution_keys = [
        (operation.lot_id, operation.unit_id, operation.precedence_seq)
        for operation in operations
    ]
    if len(execution_keys) != len(set(execution_keys)):
        raise ValueError("LOT + Unit + execution order must be unique")

    if len(dispatch_sequence) != len(set(dispatch_sequence)):
        raise ValueError("dispatch_sequence must not contain duplicates")

    if set(operation_ids) != set(dispatch_sequence):
        raise ValueError("dispatch_sequence must contain every operation_id exactly once")


def _previous_precedence_seq(
    target: OperationSpec,
    operations: tuple[OperationSpec, ...],
) -> int | None:
    earlier_steps = {
        operation.precedence_seq
        for operation in operations
        if operation.lot_id == target.lot_id
        and operation.precedence_seq < target.precedence_seq
    }
    return max(earlier_steps) if earlier_steps else None


def _precedence_earliest_start(
    *,
    target: OperationSpec,
    operations: tuple[OperationSpec, ...],
    scheduled_by_id: dict[str, ScheduledOperation],
) -> datetime | None:
    predecessors = [
        operation
        for operation in operations
        if operation.lot_id == target.lot_id
        and operation.unit_id == target.unit_id
        and operation.precedence_seq < target.precedence_seq
    ]

    if any(predecessor.operation_id not in scheduled_by_id for predecessor in predecessors):
        return None

    earliest = target.release_at
    for predecessor in predecessors:
        earliest = max(earliest, scheduled_by_id[predecessor.operation_id].end)

    return earliest


def _apply_initial_buffer_release(
    *,
    target: OperationSpec,
    operations: tuple[OperationSpec, ...],
    scheduled_operations: list[ScheduledOperation],
    earliest_start: datetime,
) -> datetime | None:
    if target.release_buffer_k is None:
        return earliest_start

    previous_step = _previous_precedence_seq(target, operations)
    if previous_step is None:
        raise ValueError("release_buffer_k cannot be set on the first routing step")

    downstream_started = any(
        scheduled.lot_id == target.lot_id
        and scheduled.precedence_seq == target.precedence_seq
        for scheduled in scheduled_operations
    )
    if downstream_started:
        return earliest_start

    upstream_ends = sorted(
        scheduled.end
        for scheduled in scheduled_operations
        if scheduled.lot_id == target.lot_id
        and scheduled.precedence_seq == previous_step
    )
    if len(upstream_ends) < target.release_buffer_k:
        return None

    buffer_release_at = upstream_ends[target.release_buffer_k - 1]
    return max(earliest_start, buffer_release_at)


def _reserve_resources(
    *,
    scheduled: ScheduledOperation,
    requirements: tuple[ResourceRequirement, ...],
    allocations: list[ResourceAllocation],
) -> None:
    for requirement in requirements:
        for segment in scheduled.segments:
            allocations.append(
                ResourceAllocation(
                    resource_code=requirement.resource_code,
                    start=segment.start,
                    end=segment.end,
                    quantity=requirement.quantity,
                )
            )


def schedule_operations(
    *,
    operations: Iterable[OperationSpec],
    dispatch_sequence: Iterable[str],
    resources: dict[str, Resource],
    calendar: WorkCalendar,
    initial_allocations: Iterable[ResourceAllocation] = (),
) -> ScheduleResult:
    """Schedule operations in caller-provided dispatch priority order.

    The function repeatedly scans the dispatch sequence and schedules the first
    operation whose routing and WIP-release conditions are currently satisfied.
    Once scheduled, its Resource allocations immediately constrain later work.
    """

    operation_tuple = tuple(operations)
    dispatch_tuple = tuple(dispatch_sequence)
    _validate_inputs(operation_tuple, dispatch_tuple)

    by_id = {operation.operation_id: operation for operation in operation_tuple}
    pending = set(by_id)
    scheduled_by_id: dict[str, ScheduledOperation] = {}
    scheduled_operations: list[ScheduledOperation] = []
    allocations = list(initial_allocations)

    while pending:
        scheduled_one = False

        for operation_id in dispatch_tuple:
            if operation_id not in pending:
                continue

            operation = by_id[operation_id]
            earliest = _precedence_earliest_start(
                target=operation,
                operations=operation_tuple,
                scheduled_by_id=scheduled_by_id,
            )
            if earliest is None:
                continue

            earliest = _apply_initial_buffer_release(
                target=operation,
                operations=operation_tuple,
                scheduled_operations=scheduled_operations,
                earliest_start=earliest,
            )
            if earliest is None:
                continue

            slot = find_earliest_feasible_slot(
                earliest_start=earliest,
                duration_minutes=operation.duration_minutes,
                requirements=operation.requirements,
                resources=resources,
                allocations=allocations,
                calendar=calendar,
            )
            scheduled = ScheduledOperation(
                operation_id=operation.operation_id,
                lot_id=operation.lot_id,
                unit_id=operation.unit_id,
                step_seq=operation.step_seq,
                process_code=operation.process_code,
                start=slot.start,
                end=slot.end,
                segments=slot.segments,
                execution_seq=operation.execution_seq,
            )
            scheduled_by_id[operation_id] = scheduled
            scheduled_operations.append(scheduled)
            _reserve_resources(
                scheduled=scheduled,
                requirements=operation.requirements,
                allocations=allocations,
            )
            pending.remove(operation_id)
            scheduled_one = True
            break

        if not scheduled_one:
            unresolved = ", ".join(sorted(pending))
            raise RuntimeError(
                "no schedulable operation remains; check routing/buffer inputs: "
                f"{unresolved}"
            )

    return ScheduleResult(
        operations=tuple(scheduled_operations),
        allocations=tuple(allocations),
    )


def aggregate_lot_process_forecast(
    scheduled_operations: Iterable[ScheduledOperation],
) -> tuple[LotProcessForecast, ...]:
    """Aggregate Unit-level schedule results into LOT × process Forecast."""

    grouped: dict[tuple[str, str], list[ScheduledOperation]] = {}
    for operation in scheduled_operations:
        grouped.setdefault((operation.lot_id, operation.process_code), []).append(operation)

    forecasts = [
        LotProcessForecast(
            lot_id=lot_id,
            process_code=process_code,
            forecast_start=min(operation.start for operation in group),
            forecast_end=max(operation.end for operation in group),
            scheduled_operation_count=len(group),
        )
        for (lot_id, process_code), group in grouped.items()
    ]
    forecasts.sort(
        key=lambda forecast: (
            forecast.lot_id,
            forecast.forecast_start,
            forecast.process_code,
        )
    )
    return tuple(forecasts)
