from datetime import datetime
from zoneinfo import ZoneInfo

import pytest

from production_control.core.candidate_evaluator import CandidateKPI
from production_control.core.pace_scheduler_adapter import ForecastReadiness
from production_control.core.priority_rules import PriorityRule
from production_control.core.replan_policy import ReplanAction
from production_control.core.risk_engine import RiskLevel
from production_control.persistence.forecast_result import (
    LotForecastSummary,
    PersistedForecastResult,
)
from production_control.persistence.replan_orchestration import (
    orchestrate_persisted_forecast,
)

SEOUL = ZoneInfo("Asia/Seoul")


def dt(hour: int) -> datetime:
    return datetime(2026, 10, 5, hour, tzinfo=SEOUL)


def forecast(
    *,
    readiness: ForecastReadiness,
    risk_level: RiskLevel,
    missing_gate_ids: tuple[str, ...] = (),
) -> PersistedForecastResult:
    return PersistedForecastResult(
        readiness=readiness,
        process_forecasts=(),
        gate_forecasts=(),
        lot_forecasts=(
            LotForecastSummary(
                lot_id="LOT-101",
                forecast_end=dt(15),
                risk_level=risk_level,
            ),
        ),
        missing_gate_ids=missing_gate_ids,
        external_barriers=(),
    )


def test_ready_persisted_forecast_drives_confirmed_replan_boundary() -> None:
    result = orchestrate_persisted_forecast(
        forecast=forecast(
            readiness=ForecastReadiness.READY,
            risk_level=RiskLevel.WARNING,
        )
    )

    assert result.risk_level is RiskLevel.WARNING
    assert result.action is ReplanAction.MONITOR_ONLY
    assert result.candidates == ()


def test_waiting_persisted_forecast_blocks_replan_generation() -> None:
    calls: list[PriorityRule] = []

    def builder(rule: PriorityRule) -> CandidateKPI:
        calls.append(rule)
        return CandidateKPI(
            candidate_id=rule.value,
            late_lot_count=0,
            total_tardiness_minutes=0,
            overtime_minutes=0,
            change_count=0,
        )

    with pytest.raises(
        ValueError,
        match="replanning requires READY Live Forecast",
    ):
        orchestrate_persisted_forecast(
            forecast=forecast(
                readiness=ForecastReadiness.WAIT,
                risk_level=RiskLevel.URGENT,
                missing_gate_ids=("GATE-101",),
            ),
            candidate_builder=builder,
        )

    assert calls == []
