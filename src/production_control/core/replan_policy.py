"""Automatic V1 replanning behavior by LOT/Gate risk level."""

from enum import StrEnum

from production_control.core.risk_engine import RiskLevel


class ReplanAction(StrEnum):
    KEEP_PLAN = "KEEP_PLAN"
    MONITOR_ONLY = "MONITOR_ONLY"
    GENERATE_CANDIDATES = "GENERATE_CANDIDATES"


def automatic_replan_action(risk_level: RiskLevel) -> ReplanAction:
    """Apply the confirmed NORMAL/WARNING/URGENT automation boundary."""

    if risk_level is RiskLevel.NORMAL:
        return ReplanAction.KEEP_PLAN
    if risk_level is RiskLevel.WARNING:
        return ReplanAction.MONITOR_ONLY
    if risk_level is RiskLevel.URGENT:
        return ReplanAction.GENERATE_CANDIDATES
    raise ValueError(f"unsupported risk level: {risk_level}")
