from production_control.core.candidate_evaluator import CandidateKPI
from production_control.core.priority_rules import PriorityRule
from production_control.core.replan_orchestrator import orchestrate_replan
from production_control.core.replan_policy import ReplanAction
from production_control.core.risk_engine import RiskLevel


def kpi(
    candidate_id: str,
    *,
    late: int = 0,
    tardiness: float = 0,
    overtime: float = 0,
    changes: int = 0,
) -> CandidateKPI:
    return CandidateKPI(
        candidate_id=candidate_id,
        late_lot_count=late,
        total_tardiness_minutes=tardiness,
        overtime_minutes=overtime,
        change_count=changes,
    )


def test_normal_keeps_plan_without_generating_candidates() -> None:
    calls: list[PriorityRule] = []

    def builder(rule: PriorityRule) -> CandidateKPI:
        calls.append(rule)
        return kpi(rule.value)

    result = orchestrate_replan(
        risk_levels=(RiskLevel.NORMAL,),
        candidate_builder=builder,
    )

    assert result.action is ReplanAction.KEEP_PLAN
    assert result.requested_rules == ()
    assert result.candidates == ()
    assert result.recommended_candidate_id is None
    assert result.requires_manager_approval is False
    assert calls == []


def test_warning_monitors_only_without_generating_candidates() -> None:
    calls: list[PriorityRule] = []

    def builder(rule: PriorityRule) -> CandidateKPI:
        calls.append(rule)
        return kpi(rule.value)

    result = orchestrate_replan(
        risk_levels=(RiskLevel.WARNING,),
        candidate_builder=builder,
    )

    assert result.action is ReplanAction.MONITOR_ONLY
    assert result.requested_rules == ()
    assert result.candidates == ()
    assert calls == []


def test_worst_risk_controls_the_orchestration_action() -> None:
    result = orchestrate_replan(
        risk_levels=(
            RiskLevel.NORMAL,
            RiskLevel.URGENT,
            RiskLevel.WARNING,
        )
    )

    assert result.risk_level is RiskLevel.URGENT
    assert result.action is ReplanAction.GENERATE_CANDIDATES


def test_urgent_without_builder_requests_all_confirmed_rules() -> None:
    result = orchestrate_replan(risk_levels=(RiskLevel.URGENT,))

    assert result.requested_rules == (
        PriorityRule.FCFS,
        PriorityRule.EDD,
        PriorityRule.SLACK,
        PriorityRule.CR,
    )
    assert result.candidates == ()
    assert result.recommended_candidate_id is None
    assert result.requires_manager_approval is False


def test_urgent_builds_four_candidates_and_recommends_d029_best() -> None:
    by_rule = {
        PriorityRule.FCFS: kpi("FCFS", late=2, tardiness=20, changes=1),
        PriorityRule.EDD: kpi("EDD", late=1, tardiness=40, changes=2),
        PriorityRule.SLACK: kpi("SLACK", late=1, tardiness=30, changes=5),
        PriorityRule.CR: kpi("CR", late=1, tardiness=30, changes=3),
    }
    calls: list[PriorityRule] = []

    def builder(rule: PriorityRule) -> CandidateKPI:
        calls.append(rule)
        return by_rule[rule]

    result = orchestrate_replan(
        risk_levels=(RiskLevel.URGENT,),
        candidate_builder=builder,
    )

    assert calls == [
        PriorityRule.FCFS,
        PriorityRule.EDD,
        PriorityRule.SLACK,
        PriorityRule.CR,
    ]
    assert result.recommended_candidate_id == "CR"
    assert result.requires_manager_approval is True
    assert [candidate.rule for candidate in result.candidates] == calls


def test_exact_candidate_kpi_tie_preserves_confirmed_rule_order() -> None:
    def builder(rule: PriorityRule) -> CandidateKPI:
        return kpi(rule.value, late=1, tardiness=10, overtime=0, changes=1)

    result = orchestrate_replan(
        risk_levels=(RiskLevel.URGENT,),
        candidate_builder=builder,
    )

    assert result.recommended_candidate_id == PriorityRule.FCFS.value


def test_empty_risk_set_defaults_to_normal_keep_plan() -> None:
    result = orchestrate_replan(risk_levels=())

    assert result.risk_level is RiskLevel.NORMAL
    assert result.action is ReplanAction.KEEP_PLAN
