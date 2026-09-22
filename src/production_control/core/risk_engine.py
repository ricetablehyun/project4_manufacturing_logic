"""Gate Forecast slack and risk classification."""

from dataclasses import dataclass
from datetime import datetime
from enum import IntEnum
from math import isfinite
from typing import Iterable


class RiskLevel(IntEnum):
    NORMAL = 0
    WARNING = 1
    URGENT = 2


@dataclass(frozen=True, slots=True)
class GateRisk:
    gate_id: str
    planned_at: datetime
    forecast_at: datetime
    slack_minutes: float
    risk_level: RiskLevel


def classify_slack(
    *,
    slack_minutes: float,
    warning_threshold_minutes: float,
) -> RiskLevel:
    """Apply the confirmed V1 Gate risk thresholds."""

    if not isfinite(slack_minutes):
        raise ValueError("slack_minutes must be finite")
    if warning_threshold_minutes < 0 or not isfinite(warning_threshold_minutes):
        raise ValueError("warning_threshold_minutes must be finite and 0 or greater")

    if slack_minutes <= 0:
        return RiskLevel.URGENT
    if slack_minutes <= warning_threshold_minutes:
        return RiskLevel.WARNING
    return RiskLevel.NORMAL


def evaluate_gate_risk(
    *,
    gate_id: str,
    planned_at: datetime,
    forecast_at: datetime,
    warning_threshold_minutes: float,
) -> GateRisk:
    """Evaluate one Gate using planned_at - forecast_at slack."""

    if not gate_id:
        raise ValueError("gate_id must not be empty")

    slack_minutes = (planned_at - forecast_at).total_seconds() / 60.0
    return GateRisk(
        gate_id=gate_id,
        planned_at=planned_at,
        forecast_at=forecast_at,
        slack_minutes=slack_minutes,
        risk_level=classify_slack(
            slack_minutes=slack_minutes,
            warning_threshold_minutes=warning_threshold_minutes,
        ),
    )


def lot_risk_level(gate_risks: Iterable[GateRisk]) -> RiskLevel:
    """LOT representative risk = worst Gate risk."""

    risks = tuple(gate_risks)
    if not risks:
        return RiskLevel.NORMAL
    return max(risk.risk_level for risk in risks)
