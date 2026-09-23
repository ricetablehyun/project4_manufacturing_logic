"""Event-driven finite-capacity dispatch for dynamic Slack / CR.

The scheduler advances a simulated decision clock. At each decision time it:
1. finds operations whose routing/release/buffer conditions are satisfied;
2. calculates LOT priority once for that decision time;
3. starts as many currently feasible operations as Resource capacity allows;
4. advances to the next meaningful completion/release/calendar/resource event.

Duration estimation, next-Gate resolution, and live RUNNING/HOLD state building
remain upstream responsibilities. This module schedules the operation durations
and priority inputs it receives.
"""

import collections.abc
from dataclasses import dataclass
from datetime import datetime

from production_control.core import dispatch_builder, priority_rules
from production_control.core.calendar_engine import WorkCalendar
from production_control.core.finite_scheduler import (
    OperationSpec,
    ScheduleResult,
    ScheduledOperation,
)
from production_control.core.resource_engine import Resource, ResourceAllocation
from production_control.core.slot_engine import find_earliest_feasible_slot


DynamicPriorityProvider = collections.abc.Callable[
    [
        datetime,
        tuple[OperationSpec, ...],
        tuple[ScheduledOperation, ...],
    ],
    collections.abc.Iterable[priority_rules.LotPriorityInput],
]


@dataclass(frozen=True, slots=True)
class EventDispatchInput:
    """Join one scheduling operation to its deterministic dispatch metadata."""

    operation: OperationSpec
    dispatch: dispatch_builder.OperationDispatchInput

    def __post_init__(self) -> None:
        if self.operation.operation_id != self.dispatch.operation_id:
            raise ValueError("operation and dispatch operation_id must match")
        if self.operation.lot_id != self.dispatch.lot_id:
            raise ValueError("operation and dispatch lot_id must match")
        if self.operation.unit_id != self.dispatch.unit_id:
            raise ValueError("operation and dispatch unit_id must match")


def _validate_inputs(items: tuple[EventDispatchInput, ...]) -> None:
    operation_ids = [item.operation.operation_id for item in items]
    if len(operation_ids) != len(set(operation_ids)):
        raise ValueError("operation_id values must be unique")

    routing_keys = [
        (
            item.operation.lot_id,
            item.operation.unit_id,
            item.operation.step_seq,
        )
        for item in items
    ]
    if len(routing_keys) != len(set(routing_keys)):
        raise ValueError("LOT + Unit + step_seq must be unique")


def _previous_step_seq(
    target: OperationSpec,
    operations: tuple[OperationSpec, ...],
) -> int | None:
    earlier_steps = {
        operation.step_seq
        for operation in operations
        if operation.lot_id == target.lot_id and operation.step_seq < target.step_seq
    }
    return max(earlier_steps) if earlier_steps else None


def _predecessors_completed(
    *,
    target: OperationSpec,
    operations: tuple[OperationSpec, ...],
    scheduled_by_id: dict[str, ScheduledOperation],
    decision_time: datetime,
) -> bool:
    predecessors = [
        operation
        for operation in operations
        if operation.lot_id == target.lot_id
        and operation.unit_id == target.unit_id
        and operation.step_seq < target.step_seq
    ]

    for predecessor in predecessors:
        scheduled = scheduled_by_id.get(predecessor.operation_id)
        if scheduled is None or scheduled.end > decision_time:
            return False
    return True


def _buffer_released(
    *,
    target: OperationSpec,
    operations: tuple[OperationSpec, ...],
    scheduled_operations: list[ScheduledOperation],
    decision_time: datetime,
) -> bool:
    if target.release_buffer_k is None:
        return True

    previous_step = _previous_step_seq(target, operations)
    if previous_step is None:
        raise ValueError("release_buffer_k cannot be set on the first routing step")

    downstream_started = any(
        scheduled.lot_id == target.lot_id
        and scheduled.step_seq == target.step_seq
        and scheduled.start <= decision_time
        for scheduled in scheduled_operations
    )
    if downstream_started:
        return True

    completed_upstream = sum(
        1
        for scheduled in scheduled_operations
        if scheduled.lot_id == target.lot_id
        and scheduled.step_seq == previous_step
        and scheduled.end <= decision_time
    )
    return completed_upstream >= target.release_buffer_k


def _structurally_ready(
    *,
    item: EventDispatchInput,
    operations: tuple[OperationSpec, ...],
    scheduled_by_id: dict[str, ScheduledOperation],
    scheduled_operations: list[ScheduledOperation],
    decision_time: datetime,
) -> bool:
    operation = item.operation
    if operation.release_at > decision_time:
        return False
    if item.dispatch.eligible_at > decision_time:
        return False
    if not _predecessors_completed(
        target=operation,
        operations=operations,
        scheduled_by_id=scheduled_by_id,
        decision_time=decision_time,
    ):
        return False
    return _buffer_released(
        target=operation,
        operations=operations,
        scheduled_operations=scheduled_operations,
        decision_time=decision_time,
    )


def _reserve_resources(
    *,
    operation: OperationSpec,
    scheduled: ScheduledOperation,
    allocations: list[ResourceAllocation],
) -> None:
    for requirement in operation.requirements:
        for segment in scheduled.segments:
            allocations.append(
                ResourceAllocation(
                    resource_code=requirement.resource_code,
                    start=segment.start,
                    end=segment.end,
                    quantity=requirement.quantity,
                )
            )


def _priority_inputs_for_decision(
    *,
    rule: priority_rules.PriorityRule,
    static_lot_priorities: tuple[priority_rules.LotPriorityInput, ...],
    dynamic_priority_provider: DynamicPriorityProvider | None,
    decision_time: datetime,
    pending_operations: tuple[OperationSpec, ...],
    scheduled_operations: tuple[ScheduledOperation, ...],
) -> tuple[priority_rules.LotPriorityInput, ...]:
    if rule in (priority_rules.PriorityRule.FCFS, priority_rules.PriorityRule.EDD):
        return static_lot_priorities

    if dynamic_priority_provider is None:
        raise ValueError("Slack / CR require dynamic_priority_provider")

    return tuple(
        dynamic_priority_provider(
            decision_time,
            pending_operations,
            scheduled_operations,
        )
    )


def _next_event_time(
    *,
    decision_time: datetime,
    pending_items: tuple[EventDispatchInput, ...],
    all_operations: tuple[OperationSpec, ...],
    scheduled_by_id: dict[str, ScheduledOperation],
    scheduled_operations: list[ScheduledOperation],
    allocations: list[ResourceAllocation],
    resources: dict[str, Resource],
    calendar: WorkCalendar,
) -> datetime:
    candidates: list[datetime] = []

    candidates.extend(
        scheduled.end
        for scheduled in scheduled_operations
        if scheduled.end > decision_time
    )
    candidates.extend(
        item.operation.release_at
        for item in pending_items
        if item.operation.release_at > decision_time
    )
    candidates.extend(
        item.dispatch.eligible_at
        for item in pending_items
        if item.dispatch.eligible_at > decision_time
    )
    candidates.extend(
        allocation.end
        for allocation in allocations
        if allocation.end > decision_time
    )

    if not calendar.is_working_time(decision_time):
        next_open = calendar.next_work_start(decision_time)
        if next_open > decision_time:
            candidates.append(next_open)

    for item in pending_items:
        if not _structurally_ready(
            item=item,
            operations=all_operations,
            scheduled_by_id=scheduled_by_id,
            scheduled_operations=scheduled_operations,
            decision_time=decision_time,
        ):
            continue

        slot = find_earliest_feasible_slot(
            earliest_start=decision_time,
            duration_minutes=item.operation.duration_minutes,
            requirements=item.operation.requirements,
            resources=resources,
            allocations=allocations,
            calendar=calendar,
        )
        if slot.start > decision_time:
            candidates.append(slot.start)

    future = [candidate for candidate in candidates if candidate > decision_time]
    if not future:
        unresolved = ", ".join(
            sorted(item.operation.operation_id for item in pending_items)
        )
        raise RuntimeError(
            "no future dispatch event found; check routing/buffer/resource inputs: "
            f"{unresolved}"
        )

    return min(future)


def schedule_operations_event_driven(
    *,
    items: collections.abc.Iterable[EventDispatchInput],
    rule: priority_rules.PriorityRule,
    static_lot_priorities: collections.abc.Iterable[
        priority_rules.LotPriorityInput
    ],
    resources: dict[str, Resource],
    calendar: WorkCalendar,
    start_time: datetime,
    dynamic_priority_provider: DynamicPriorityProvider | None = None,
    initial_allocations: collections.abc.Iterable[ResourceAllocation] = (),
) -> ScheduleResult:
    """Schedule work using the confirmed event-driven dispatch clock."""

    item_tuple = tuple(items)
    _validate_inputs(item_tuple)

    if not item_tuple:
        return ScheduleResult(
            operations=(),
            allocations=tuple(initial_allocations),
        )

    operation_tuple = tuple(item.operation for item in item_tuple)
    by_id = {item.operation.operation_id: item for item in item_tuple}
    pending = set(by_id)
    scheduled_by_id: dict[str, ScheduledOperation] = {}
    scheduled_operations: list[ScheduledOperation] = []
    allocations = list(initial_allocations)
    static_priorities = tuple(static_lot_priorities)
    decision_time = start_time

    while pending:
        pending_items = tuple(by_id[operation_id] for operation_id in pending)
        ready_items = tuple(
            item
            for item in pending_items
            if _structurally_ready(
                item=item,
                operations=operation_tuple,
                scheduled_by_id=scheduled_by_id,
                scheduled_operations=scheduled_operations,
                decision_time=decision_time,
            )
        )

        if ready_items:
            priority_inputs = _priority_inputs_for_decision(
                rule=rule,
                static_lot_priorities=static_priorities,
                dynamic_priority_provider=dynamic_priority_provider,
                decision_time=decision_time,
                pending_operations=tuple(
                    by_id[operation_id].operation for operation_id in pending
                ),
                scheduled_operations=tuple(scheduled_operations),
            )

            ready_lot_ids = {item.operation.lot_id for item in ready_items}
            priority_lot_ids = {lot.lot_id for lot in priority_inputs}
            missing = ready_lot_ids - priority_lot_ids
            if missing:
                missing_text = ", ".join(sorted(missing))
                raise ValueError(
                    "priority inputs missing ready LOTs: "
                    f"{missing_text}"
                )

            dispatch_sequence = dispatch_builder.build_dispatch_sequence(
                lots=priority_inputs,
                operations=(item.dispatch for item in ready_items),
                rule=rule,
            )

            for operation_id in dispatch_sequence:
                if operation_id not in pending:
                    continue

                item = by_id[operation_id]
                slot = find_earliest_feasible_slot(
                    earliest_start=decision_time,
                    duration_minutes=item.operation.duration_minutes,
                    requirements=item.operation.requirements,
                    resources=resources,
                    allocations=allocations,
                    calendar=calendar,
                )
                if slot.start != decision_time:
                    continue

                scheduled = ScheduledOperation(
                    operation_id=item.operation.operation_id,
                    lot_id=item.operation.lot_id,
                    unit_id=item.operation.unit_id,
                    step_seq=item.operation.step_seq,
                    process_code=item.operation.process_code,
                    start=slot.start,
                    end=slot.end,
                    segments=slot.segments,
                )
                scheduled_by_id[operation_id] = scheduled
                scheduled_operations.append(scheduled)
                _reserve_resources(
                    operation=item.operation,
                    scheduled=scheduled,
                    allocations=allocations,
                )
                pending.remove(operation_id)

        if pending:
            pending_items = tuple(by_id[operation_id] for operation_id in pending)
            decision_time = _next_event_time(
                decision_time=decision_time,
                pending_items=pending_items,
                all_operations=operation_tuple,
                scheduled_by_id=scheduled_by_id,
                scheduled_operations=scheduled_operations,
                allocations=allocations,
                resources=resources,
                calendar=calendar,
            )

    return ScheduleResult(
        operations=tuple(scheduled_operations),
        allocations=tuple(allocations),
    )
