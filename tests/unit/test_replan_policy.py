from production_control.core.replan_policy import ReplanAction, automatic_replan_action
from production_control.core.risk_engine import RiskLevel


def test_normal_keeps_current_plan() -> None:
    assert automatic_replan_action(RiskLevel.NORMAL) is ReplanAction.KEEP_PLAN


def test_warning_updates_monitoring_without_auto_candidates() -> None:
    assert automatic_replan_action(RiskLevel.WARNING) is ReplanAction.MONITOR_ONLY


def test_urgent_generates_candidates_but_does_not_auto_apply() -> None:
    assert (
        automatic_replan_action(RiskLevel.URGENT)
        is ReplanAction.GENERATE_CANDIDATES
    )
