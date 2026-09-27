"""Preserve persisted ScheduleTask priority ranks in Live Forecast dispatch.

ScheduleTask priority_rank is a LOT x routing-step planning value. This adapter
maps each current EventDispatchInput to its matching persisted task and supplies
an explicit ready-operation order to the policy-neutral event scheduler.
"""

from collections.abc import Iterable
from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.orm import Session

from production_control.core.dispatch_builder import operation_tie_break_key
from production_control.core.event_scheduler import (
    EventDispatchInput,
    ReadyDispatchProvider,
)
from production_control.persistence.models import (
    ProcessRow,
    RoutingStepRow,
    SchedulePlanRow,
    ScheduleTaskRow,
)
from production_control.persistence.plan_lifecycle import load_current_approved_plan


@dataclass(frozen=True, slots=True)
class PlanTaskPriority:
    schedule_task_id: str
    lot_id: str
    routing_step_id: str
    step_seq: int
    process_code: str
    priority_rank: int
    technical_order: int

    @property
    def operation_key(self) -> tuple[str, int, str]:
        return (self.lot_id, self.step_seq, self.process_code)


def load_plan_task_priorities(
    *,
    session: Session,
    plan_id: str,
) -> tuple[PlanTaskPriority, ...]:
    """Load LOT x process priority rows for one explicit SchedulePlan."""

    if session.get(SchedulePlanRow, plan_id) is None:
        raise ValueError(f"unknown plan_id: {plan_id}")

    rows = session.execute(
        select(ScheduleTaskRow, RoutingStepRow, ProcessRow)
        .join(
            RoutingStepRow,
            ScheduleTaskRow.routing_step_id == RoutingStepRow.routing_step_id,
        )
        .join(ProcessRow, RoutingStepRow.process_id == ProcessRow.process_id)
        .where(ScheduleTaskRow.plan_id == plan_id)
        .order_by(
            ScheduleTaskRow.priority_rank,
            ScheduleTaskRow.schedule_task_id,
        )
    ).all()

    priorities: list[PlanTaskPriority] = []
    seen_keys: set[tuple[str, int, str]] = set()
    for technical_order, (task, step, process) in enumerate(rows):
        if task.priority_rank <= 0:
            raise ValueError(
                "ScheduleTask priority_rank must be greater than 0: "
                f"{task.schedule_task_id}"
            )

        priority = PlanTaskPriority(
            schedule_task_id=task.schedule_task_id,
            lot_id=task.lot_id,
            routing_step_id=task.routing_step_id,
            step_seq=step.seq_no,
            process_code=process.process_code,
            priority_rank=task.priority_rank,
            technical_order=technical_order,
        )
        if priority.operation_key in seen_keys:
            raise ValueError(
                "SchedulePlan contains duplicate LOT x process task mapping: "
                f"{priority.operation_key}"
            )
        seen_keys.add(priority.operation_key)
        priorities.append(priority)

    if not priorities:
        raise ValueError(f"SchedulePlan has no ScheduleTask rows: {plan_id}")

    return tuple(priorities)


def build_plan_ready_dispatch_provider(
    *,
    session: Session,
    plan_id: str,
    items: Iterable[EventDispatchInput],
) -> ReadyDispatchProvider:
    """Build a ready-operation provider from one persisted plan snapshot.

    The production key is ScheduleTask.priority_rank. If two persisted tasks
    accidentally share the same rank, schedule_task_id ordering is used only as
    a deterministic technical tie-break; it does not create a new planning
    policy. Inside the same task, the already-confirmed operation tie-break is
    reused for Forecast reproducibility.
    """

    item_tuple = tuple(items)
    priorities = load_plan_task_priorities(session=session, plan_id=plan_id)
    priority_by_key = {priority.operation_key: priority for priority in priorities}

    priority_by_operation_id: dict[str, PlanTaskPriority] = {}
    for item in item_tuple:
        key = (
            item.operation.lot_id,
            item.operation.step_seq,
            item.operation.process_code,
        )
        priority = priority_by_key.get(key)
        if priority is None:
            raise ValueError(
                "current Forecast operation has no matching ScheduleTask in plan "
                f"{plan_id}: {item.operation.operation_id} / {key}"
            )
        priority_by_operation_id[item.operation.operation_id] = priority

    def provider(
        _decision_time,
        ready_items: tuple[EventDispatchInput, ...],
    ) -> tuple[str, ...]:
        unknown = [
            item.operation.operation_id
            for item in ready_items
            if item.operation.operation_id not in priority_by_operation_id
        ]
        if unknown:
            raise ValueError(
                "ready operation was not part of the approved-plan Forecast input: "
                + ", ".join(sorted(unknown))
            )

        ranked = sorted(
            ready_items,
            key=lambda item: (
                priority_by_operation_id[
                    item.operation.operation_id
                ].priority_rank,
                priority_by_operation_id[
                    item.operation.operation_id
                ].technical_order,
                operation_tie_break_key(item.dispatch),
                item.operation.operation_id,
            ),
        )
        return tuple(item.operation.operation_id for item in ranked)

    return provider


def build_current_plan_ready_dispatch_provider(
    *,
    session: Session,
    items: Iterable[EventDispatchInput],
) -> ReadyDispatchProvider:
    """Build Live Forecast dispatch from the latest approved plan version."""

    current = load_current_approved_plan(session=session)
    return build_plan_ready_dispatch_provider(
        session=session,
        plan_id=current.plan_id,
        items=items,
    )
