"""Approve one transient replan candidate after server-side recomputation.

D057 keeps candidate details off the client approval contract. The caller only
selects a candidate from a specific parent plan / as-of snapshot; this service
rebuilds that candidate from persisted state before delegating persistence to
the existing approved-plan lifecycle boundary.
"""

from dataclasses import dataclass
from datetime import datetime

from sqlalchemy.orm import Session

from production_control.core.replan_policy import ReplanAction
from production_control.persistence.live_forecast import LiveForecastConfig
from production_control.persistence.plan_lifecycle import (
    ApprovedPlanTaskDraft,
    load_current_approved_plan,
    persist_approved_replan,
)
from production_control.persistence.replan_candidates import build_replan_candidates


@dataclass(frozen=True, slots=True)
class ReplanApprovalResult:
    plan_id: str
    version: int
    status: str
    parent_plan_id: str
    priority_rule: str
    approved_at: datetime
    selected_candidate_id: str


def approve_replan_candidate(
    *,
    session: Session,
    parent_plan_id: str,
    candidate_id: str,
    candidate_as_of: datetime,
    approved_at: datetime,
    plan_id: str,
    config: LiveForecastConfig,
) -> ReplanApprovalResult:
    """Recompute and persist one manager-selected candidate.

    The service never accepts client-supplied KPI or task values. Parent-plan
    staleness is checked before recomputation, while execution-state staleness
    after candidate_as_of is rejected by the existing Live Forecast time-travel
    validation used by build_replan_candidates().
    """

    if not parent_plan_id:
        raise ValueError("parent_plan_id must not be empty")
    if not candidate_id:
        raise ValueError("candidate_id must not be empty")
    if candidate_as_of.tzinfo is None or candidate_as_of.utcoffset() is None:
        raise ValueError("candidate_as_of must be timezone-aware")
    if approved_at.tzinfo is None or approved_at.utcoffset() is None:
        raise ValueError("approved_at must be timezone-aware")
    if not plan_id:
        raise ValueError("plan_id must not be empty")

    current = load_current_approved_plan(session=session)
    if current.plan_id != parent_plan_id:
        raise ValueError(
            "replan approval is stale: parent plan is no longer current: "
            f"current={current.plan_id}, supplied={parent_plan_id}"
        )

    snapshot = build_replan_candidates(
        session=session,
        as_of=candidate_as_of,
        config=config,
    )
    if snapshot.parent_plan_id != parent_plan_id:
        raise ValueError(
            "replan approval is stale: candidate parent changed during recomputation"
        )
    if snapshot.action is not ReplanAction.GENERATE_CANDIDATES:
        raise ValueError(
            "replan approval is stale: current policy no longer generates candidates"
        )

    selected = next(
        (
            candidate
            for candidate in snapshot.candidates
            if candidate.candidate_id == candidate_id
        ),
        None,
    )
    if selected is None:
        raise LookupError(f"unknown replan candidate_id: {candidate_id}")

    drafts = tuple(
        ApprovedPlanTaskDraft(
            schedule_task_id=f"TASK::{plan_id}::{index:03d}",
            lot_id=task.lot_id,
            routing_step_id=task.routing_step_id,
            target_start=task.target_start,
            target_end=task.target_end,
            target_qty=task.target_qty,
            priority_rank=task.priority_rank,
        )
        for index, task in enumerate(selected.tasks, start=1)
    )
    plan = persist_approved_replan(
        session=session,
        plan_id=plan_id,
        parent_plan_id=parent_plan_id,
        priority_rule=selected.rule,
        trigger_reason=snapshot.risk_level.name,
        approved_at=approved_at,
        selected_kpi=selected.kpi,
        tasks=drafts,
    )

    return ReplanApprovalResult(
        plan_id=plan.plan_id,
        version=plan.version,
        status=plan.status,
        parent_plan_id=plan.parent_plan_id,
        priority_rule=plan.priority_rule,
        approved_at=plan.approved_at,
        selected_candidate_id=selected.candidate_id,
    )
