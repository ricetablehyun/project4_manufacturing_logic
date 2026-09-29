"""Evaluate whether one candidate schedule respects urgent-LOT dispatch policy.

The policy is intentionally separate from FCFS / EDD / Slack / CR. Those rules
still build candidate schedules. This module then replays each decision point
and rejects a candidate only when a non-urgent ready operation consumes capacity
that an urgent ready operation could have used at the same time.
"""

from dataclasses import dataclass
from itertools import groupby

from production_control.core.calendar_engine import WorkCalendar
from production_control.core.event_scheduler import (
    EventDispatchInput,
    _structurally_ready,
)
from production_control.core.finite_scheduler import ScheduledOperation, ScheduleResult
from production_control.core.resource_engine import Resource, ResourceAllocation
from production_control.core.slot_engine import find_earliest_feasible_slot
from production_control.domain.enums import OperationState


@dataclass(frozen=True, slots=True)
class UrgentDispatchPolicyResult:
    compliant: bool
    violation_reason: str | None = None


def _reserve_scheduled_operation(
    *,
    item: EventDispatchInput,
    scheduled: ScheduledOperation,
    allocations: list[ResourceAllocation],
) -> None:
    for requirement in item.operation.requirements:
        for segment in scheduled.segments:
            allocations.append(
                ResourceAllocation(
                    resource_code=requirement.resource_code,
                    start=segment.start,
                    end=segment.end,
                    quantity=requirement.quantity,
                )
            )


def _can_start_now(
    *,
    item: EventDispatchInput,
    decision_time,
    resources: dict[str, Resource],
    allocations: list[ResourceAllocation],
    calendar: WorkCalendar,
) -> bool:
    slot = find_earliest_feasible_slot(
        earliest_start=decision_time,
        duration_minutes=item.operation.duration_minutes,
        requirements=item.operation.requirements,
        resources=resources,
        allocations=allocations,
        calendar=calendar,
    )
    return slot.start == decision_time


def evaluate_urgent_lot_dispatch_policy(
    *,
    items: tuple[EventDispatchInput, ...],
    schedule: ScheduleResult,
    resources: dict[str, Resource],
    calendar: WorkCalendar,
    urgent_lot_ids: set[str],
) -> UrgentDispatchPolicyResult:
    """Reject only real ready/resource conflicts that push an urgent LOT back.

    A non-urgent operation is allowed to run while an urgent LOT is structurally
    unavailable. It is also allowed to start in parallel when enough capacity
    remains for the urgent operation at the same decision time.
    """

    if not urgent_lot_ids:
        return UrgentDispatchPolicyResult(compliant=True)

    item_by_id = {item.operation.operation_id: item for item in items}
    if set(item_by_id) != {operation.operation_id for operation in schedule.operations}:
        raise ValueError("policy evaluation requires the same operations as the schedule")

    pending = set(item_by_id)
    all_operations = tuple(item.operation for item in items)
    scheduled_by_id: dict[str, ScheduledOperation] = {}
    scheduled_history: list[ScheduledOperation] = []
    allocations: list[ResourceAllocation] = []

    previous_start = None
    for decision_time, grouped in groupby(
        schedule.operations,
        key=lambda operation: operation.start,
    ):
        if previous_start is not None and decision_time < previous_start:
            raise ValueError("schedule operations must be ordered by nondecreasing start time")
        previous_start = decision_time
        group = tuple(grouped)

        initial_ready = tuple(
            item_by_id[operation_id]
            for operation_id in pending
            if _structurally_ready(
                item=item_by_id[operation_id],
                operations=all_operations,
                scheduled_by_id=scheduled_by_id,
                scheduled_operations=scheduled_history,
                decision_time=decision_time,
            )
        )
        initial_ready_ids = {item.operation.operation_id for item in initial_ready}

        # RUNNING work is continued before a new dispatch decision and is not
        # preempted by D073.
        for scheduled in group:
            item = item_by_id[scheduled.operation_id]
            if item.dispatch.state is not OperationState.RUNNING:
                continue
            if scheduled.operation_id not in pending:
                continue
            _reserve_scheduled_operation(
                item=item,
                scheduled=scheduled,
                allocations=allocations,
            )
            scheduled_by_id[scheduled.operation_id] = scheduled
            scheduled_history.append(scheduled)
            pending.remove(scheduled.operation_id)

        ready_ids = initial_ready_ids & pending

        for scheduled in group:
            item = item_by_id[scheduled.operation_id]
            if item.dispatch.state is OperationState.RUNNING:
                continue
            if scheduled.operation_id not in pending:
                continue
            if scheduled.operation_id not in ready_ids:
                raise ValueError(
                    "policy replay found a scheduled operation that was not ready: "
                    f"{scheduled.operation_id}"
                )

            if item.operation.lot_id not in urgent_lot_ids:
                urgent_ready = [
                    item_by_id[operation_id]
                    for operation_id in ready_ids
                    if operation_id in pending
                    and item_by_id[operation_id].operation.lot_id in urgent_lot_ids
                ]
                for urgent_item in urgent_ready:
                    if not _can_start_now(
                        item=urgent_item,
                        decision_time=decision_time,
                        resources=resources,
                        allocations=allocations,
                        calendar=calendar,
                    ):
                        continue

                    after_nonurgent = list(allocations)
                    _reserve_scheduled_operation(
                        item=item,
                        scheduled=scheduled,
                        allocations=after_nonurgent,
                    )
                    if _can_start_now(
                        item=urgent_item,
                        decision_time=decision_time,
                        resources=resources,
                        allocations=after_nonurgent,
                        calendar=calendar,
                    ):
                        continue

                    urgent_resources = {
                        requirement.resource_code
                        for requirement in urgent_item.operation.requirements
                    }
                    nonurgent_resources = {
                        requirement.resource_code
                        for requirement in item.operation.requirements
                    }
                    shared_resources = sorted(urgent_resources & nonurgent_resources)
                    resource_text = ", ".join(shared_resources) or "공유 제한 자원"
                    return UrgentDispatchPolicyResult(
                        compliant=False,
                        violation_reason=(
                            f"긴급 LOT {urgent_item.operation.lot_id} 작업이 가능한 시점에 "
                            f"비긴급 LOT {item.operation.lot_id}가 {resource_text}을(를) "
                            "먼저 점유했습니다."
                        ),
                    )

            _reserve_scheduled_operation(
                item=item,
                scheduled=scheduled,
                allocations=allocations,
            )
            scheduled_by_id[scheduled.operation_id] = scheduled
            scheduled_history.append(scheduled)
            pending.remove(scheduled.operation_id)

    if pending:
        unresolved = ", ".join(sorted(pending))
        raise ValueError(f"policy replay did not cover scheduled operations: {unresolved}")

    return UrgentDispatchPolicyResult(compliant=True)
