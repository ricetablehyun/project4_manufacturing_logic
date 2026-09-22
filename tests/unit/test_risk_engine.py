from datetime import datetime
from zoneinfo import ZoneInfo

import pytest

from production_control.core.risk_engine import (
    RiskLevel,
    classify_slack,
    evaluate_gate_risk,
    lot_risk_level,
)

SEOUL = ZoneInfo("Asia/Seoul")


def dt(hour: int, minute: int = 0) -> datetime:
    return datetime(2026, 10, 5, hour, minute, tzinfo=SEOUL)


def test_positive_slack_above_threshold_is_normal() -> None:
    assert classify_slack(
        slack_minutes=121,
        warning_threshold_minutes=120,
    ) is RiskLevel.NORMAL


def test_positive_slack_at_threshold_is_warning() -> None:
    assert classify_slack(
        slack_minutes=120,
        warning_threshold_minutes=120,
    ) is RiskLevel.WARNING


def test_zero_slack_is_urgent() -> None:
    assert classify_slack(
        slack_minutes=0,
        warning_threshold_minutes=120,
    ) is RiskLevel.URGENT


def test_negative_slack_is_urgent() -> None:
    assert classify_slack(
        slack_minutes=-15,
        warning_threshold_minutes=120,
    ) is RiskLevel.URGENT


def test_gate_risk_uses_planned_minus_forecast() -> None:
    risk = evaluate_gate_risk(
        gate_id="GATE-01",
        planned_at=dt(15),
        forecast_at=dt(14, 30),
        warning_threshold_minutes=120,
    )

    assert risk.slack_minutes == 30
    assert risk.risk_level is RiskLevel.WARNING


def test_lot_risk_is_worst_gate() -> None:
    normal = evaluate_gate_risk(
        gate_id="G1",
        planned_at=dt(15),
        forecast_at=dt(12),
        warning_threshold_minutes=120,
    )
    warning = evaluate_gate_risk(
        gate_id="G2",
        planned_at=dt(15),
        forecast_at=dt(14),
        warning_threshold_minutes=120,
    )
    urgent = evaluate_gate_risk(
        gate_id="G3",
        planned_at=dt(15),
        forecast_at=dt(15, 10),
        warning_threshold_minutes=120,
    )

    assert lot_risk_level((normal, warning, urgent)) is RiskLevel.URGENT


def test_lot_without_gate_risk_defaults_to_normal() -> None:
    assert lot_risk_level(()) is RiskLevel.NORMAL


def test_negative_warning_threshold_is_rejected() -> None:
    with pytest.raises(ValueError):
        classify_slack(
            slack_minutes=30,
            warning_threshold_minutes=-1,
        )
