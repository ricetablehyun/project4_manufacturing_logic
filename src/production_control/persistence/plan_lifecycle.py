"""Persistence helpers for approved SchedulePlan version history.

Confirmed project behavior:
- Live Forecast is not persisted on every calculation.
- Replan candidates stay calculation results until a manager approves one.
- Approved plans are preserved by version instead of being overwritten.
- The current plan is the latest approved version.

This module therefore persists only the selected/approved plan snapshot. It does
not persist all transient FCFS/EDD/Slack/CR candidates.
"""

from dataclasses import dataclass
from datetime import datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from production_control.core.candidate_evaluator import CandidateKPI
from production_control.core.priority_rules import PriorityRule
from production_control.persistence.models import SchedulePlanRow, ScheduleTaskRow


@dataclass(frozen=True, slots=True)
class ApprovedPlanTaskDraft:
    """Explicit LOT x RoutingStep task values selected for approval."""

    schedule_task_id: str
    lot_id: str
    routing_step_id: str
    target_start: datetime
    target_end: datetime
    target_qty: int
    priority_rank: int

    def __post_init__(self) -> None:
        if not self.schedule_task_id:
            raise ValueError("schedule_task_id must not be empty")
        if not self.lot_id:
            raise ValueError("lot_id must not be empty")
        if not self.routing_step_id:
            raise ValueError("routing_step_id must not be empty")
        if self.target_end < self.target_start:
            raise ValueError("target_end must be at or after target_start")
        if self.target_qty <= 0:
            raise ValueError("target_qty must be greater than 0")
        if self.priority_rank <= 0:
            raise ValueError("priority_rank must be greater than 0")


def load_current_approved_plan(*, session: Session) -> SchedulePlanRow:
    """Return the latest approved SchedulePlan version.

    Historical versions remain APPROVED because each was approved at its own
    point in time. Current-plan identity is derived from the greatest approved
    version, matching the confirmed "latest plan" presentation rule without
    deleting or mutating plan history.
    """

    rows = session.scalars(
        select(SchedulePlanRow)
        .where(SchedulePlanRow.status == "APPROVED")
        .order_by(SchedulePlanRow.version.desc())
    ).all()
    if not rows:
        raise ValueError("no approved SchedulePlan exists")

    highest_version = rows[0].version
    highest = [row for row in rows if row.version == highest_version]
    if len(highest) != 1:
        raise ValueError(
            "approved SchedulePlan version is ambiguous: "
            f"multiple rows use version {highest_version}"
        )
    return highest[0]


def persist_approved_replan(
    *,
    session: Session,
    plan_id: str,
    parent_plan_id: str,
    priority_rule: PriorityRule,
    trigger_reason: str,
    approved_at: datetime,
    selected_kpi: CandidateKPI,
    tasks: tuple[ApprovedPlanTaskDraft, ...],
) -> SchedulePlanRow:
    """Persist one manager-approved replan as the next official version.

    Candidate task values are supplied explicitly by the caller. This service
    intentionally does not infer target_qty or invent LOT x process tasks from
    partial scheduler state.
    """

    if not plan_id:
        raise ValueError("plan_id must not be empty")
    if not parent_plan_id:
        raise ValueError("parent_plan_id must not be empty")
    if not trigger_reason:
        raise ValueError("trigger_reason must not be empty")
    if not tasks:
        raise ValueError("approved replan requires at least one ScheduleTask")
    if session.get(SchedulePlanRow, plan_id) is not None:
        raise ValueError(f"plan_id already exists: {plan_id}")

    current = load_current_approved_plan(session=session)
    if current.plan_id != parent_plan_id:
        raise ValueError(
            "replan parent must be the current approved plan: "
            f"current={current.plan_id}, supplied={parent_plan_id}"
        )

    task_ids = [task.schedule_task_id for task in tasks]
    if len(task_ids) != len(set(task_ids)):
        raise ValueError("schedule_task_id values must be unique within a plan")

    task_keys = [(task.lot_id, task.routing_step_id) for task in tasks]
    if len(task_keys) != len(set(task_keys)):
        raise ValueError(
            "approved plan must contain at most one task per LOT x RoutingStep"
        )

    plan = SchedulePlanRow(
        plan_id=plan_id,
        version=current.version + 1,
        plan_kind="REPLAN",
        priority_rule=priority_rule.value,
        status="APPROVED",
        parent_plan_id=current.plan_id,
        trigger_reason=trigger_reason,
        created_at=approved_at,
        approved_at=approved_at,
        late_lot_count=selected_kpi.late_lot_count,
        total_tardiness_minutes=selected_kpi.total_tardiness_minutes,
        overtime_minutes=selected_kpi.overtime_minutes,
        change_count=selected_kpi.change_count,
    )
    session.add(plan)

    for task in tasks:
        session.add(
            ScheduleTaskRow(
                schedule_task_id=task.schedule_task_id,
                plan_id=plan_id,
                lot_id=task.lot_id,
                routing_step_id=task.routing_step_id,
                target_start=task.target_start,
                target_end=task.target_end,
                target_qty=task.target_qty,
                priority_rank=task.priority_rank,
            )
        )

    session.commit()
    return plan
