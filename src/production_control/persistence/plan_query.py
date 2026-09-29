"""Read-only queries for the currently approved production plan."""

from dataclasses import dataclass
from datetime import datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from production_control.persistence.models import (
    ProcessRow,
    RoutingStepRow,
    ScheduleTaskRow,
)
from production_control.persistence.plan_lifecycle import load_current_approved_plan


@dataclass(frozen=True, slots=True)
class CurrentPlanTask:
    lot_id: str
    routing_step_id: str
    process_code: str
    seq_no: int
    target_start: datetime
    target_end: datetime
    target_qty: int
    priority_rank: int


@dataclass(frozen=True, slots=True)
class CurrentPlanSnapshot:
    plan_id: str
    version: int
    priority_rule: str
    tasks: tuple[CurrentPlanTask, ...]


def load_current_plan_snapshot(*, session: Session) -> CurrentPlanSnapshot:
    """Return the latest approved plan and its LOT x process tasks."""

    plan = load_current_approved_plan(session=session)
    rows = session.execute(
        select(ScheduleTaskRow, RoutingStepRow, ProcessRow)
        .join(
            RoutingStepRow,
            ScheduleTaskRow.routing_step_id == RoutingStepRow.routing_step_id,
        )
        .join(ProcessRow, RoutingStepRow.process_id == ProcessRow.process_id)
        .where(ScheduleTaskRow.plan_id == plan.plan_id)
        .order_by(
            ScheduleTaskRow.priority_rank,
            ScheduleTaskRow.lot_id,
            RoutingStepRow.seq_no,
        )
    ).all()

    return CurrentPlanSnapshot(
        plan_id=plan.plan_id,
        version=plan.version,
        priority_rule=plan.priority_rule,
        tasks=tuple(
            CurrentPlanTask(
                lot_id=task.lot_id,
                routing_step_id=task.routing_step_id,
                process_code=process.process_code,
                seq_no=step.seq_no,
                target_start=task.target_start,
                target_end=task.target_end,
                target_qty=task.target_qty,
                priority_rank=task.priority_rank,
            )
            for task, step, process in rows
        ),
    )
