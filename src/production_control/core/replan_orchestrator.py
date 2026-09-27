"""Coordinate Forecast risk with the confirmed V1 replanning boundary.

This module intentionally does not know about persistence, scheduling, or UI.
It only decides whether candidate generation is allowed, requests the four
confirmed dispatching-rule candidates for URGENT risk, and selects the
lexicographically best KPI result. Candidate application remains a separate
manager approval action.
"""

from collections.abc import Callable, Iterable
from dataclasses import dataclass

from production_control.core.candidate_evaluator import CandidateKPI, select_candidate
from production_control.core.priority_rules import PriorityRule
from production_control.core.replan_policy import ReplanAction, automatic_replan_action
from production_control.core.risk_engine import RiskLevel

CandidateBuilder = Callable[[PriorityRule], CandidateKPI]

_CANDIDATE_RULES = (
    PriorityRule.FCFS,
    PriorityRule.EDD,
    PriorityRule.SLACK,
    PriorityRule.CR,
)


@dataclass(frozen=True, slots=True)
class ReplanCandidateResult:
    rule: PriorityRule
    kpi: CandidateKPI


@dataclass(frozen=True, slots=True)
class ReplanOrchestrationResult:
    """One controller-cycle result for the current Live Forecast."""

    risk_level: RiskLevel
    action: ReplanAction
    requested_rules: tuple[PriorityRule, ...]
    candidates: tuple[ReplanCandidateResult, ...]
    recommended_candidate_id: str | None
    requires_manager_approval: bool


def representative_risk(risk_levels: Iterable[RiskLevel]) -> RiskLevel:
    """Use the worst current LOT/Gate risk as the orchestration trigger."""

    levels = tuple(risk_levels)
    if not levels:
        return RiskLevel.NORMAL
    return max(levels)


def orchestrate_replan(
    *,
    risk_levels: Iterable[RiskLevel],
    candidate_builder: CandidateBuilder | None = None,
) -> ReplanOrchestrationResult:
    """Apply NORMAL/WARNING/URGENT behavior without auto-applying a plan.

    NORMAL and WARNING never invoke candidate generation. URGENT requests the
    four confirmed V1 rules. If a builder is supplied, all four are evaluated
    and the D029 lexicographic recommendation is returned. Even then, the
    result only recommends a candidate; manager approval is still required.
    """

    risk_level = representative_risk(risk_levels)
    action = automatic_replan_action(risk_level)

    if action is not ReplanAction.GENERATE_CANDIDATES:
        return ReplanOrchestrationResult(
            risk_level=risk_level,
            action=action,
            requested_rules=(),
            candidates=(),
            recommended_candidate_id=None,
            requires_manager_approval=False,
        )

    if candidate_builder is None:
        return ReplanOrchestrationResult(
            risk_level=risk_level,
            action=action,
            requested_rules=_CANDIDATE_RULES,
            candidates=(),
            recommended_candidate_id=None,
            requires_manager_approval=False,
        )

    candidates = tuple(
        ReplanCandidateResult(
            rule=rule,
            kpi=candidate_builder(rule),
        )
        for rule in _CANDIDATE_RULES
    )
    recommended = select_candidate(candidate.kpi for candidate in candidates)

    return ReplanOrchestrationResult(
        risk_level=risk_level,
        action=action,
        requested_rules=_CANDIDATE_RULES,
        candidates=candidates,
        recommended_candidate_id=recommended.candidate_id,
        requires_manager_approval=True,
    )
