from datetime import UTC, datetime
from types import SimpleNamespace

import pytest

from production_control.core.candidate_evaluator import CandidateKPI
from production_control.core.priority_rules import PriorityRule
from production_control.core.replan_policy import ReplanAction
from production_control.core.risk_engine import RiskLevel
from production_control.persistence import replan_approval
from production_control.persistence.live_forecast import LiveForecastConfig
from production_control.persistence.replan_candidates import (
    PersistedReplanCandidate,
    PersistedReplanCandidateSnapshot,
)


def test_approval_rejects_candidate_that_violates_urgent_lot_policy(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    as_of = datetime(2026, 10, 5, 9, tzinfo=UTC)
    candidate = PersistedReplanCandidate(
        candidate_id="FCFS",
        rule=PriorityRule.FCFS,
        kpi=CandidateKPI(
            candidate_id="FCFS",
            late_lot_count=1,
            total_tardiness_minutes=60,
            overtime_minutes=0,
            change_count=2,
        ),
        tasks=(),
        policy_compliant=False,
        policy_violation_reason=(
            "긴급 LOT LOT-URGENT 작업이 가능한 시점에 비긴급 LOT LOT-NORMAL이 "
            "TUNING_STATION을 먼저 점유했습니다."
        ),
    )
    snapshot = PersistedReplanCandidateSnapshot(
        parent_plan_id="PLAN-1",
        parent_plan_version=1,
        as_of=as_of,
        risk_level=RiskLevel.URGENT,
        action=ReplanAction.GENERATE_CANDIDATES,
        recommended_candidate_id=None,
        requires_manager_approval=False,
        candidates=(candidate,),
    )

    monkeypatch.setattr(
        replan_approval,
        "load_current_approved_plan",
        lambda *, session: SimpleNamespace(plan_id="PLAN-1"),
    )
    monkeypatch.setattr(
        replan_approval,
        "build_replan_candidates",
        lambda *, session, as_of, config: snapshot,
    )

    with pytest.raises(ValueError, match="replan candidate is not approvable"):
        replan_approval.approve_replan_candidate(
            session=object(),
            parent_plan_id="PLAN-1",
            candidate_id="FCFS",
            candidate_as_of=as_of,
            approved_at=as_of,
            plan_id="PLAN-2",
            config=LiveForecastConfig(
                calendar_id="CALENDAR-NORMAL",
                pace_min_samples=3,
                warning_threshold_minutes=120,
            ),
        )
