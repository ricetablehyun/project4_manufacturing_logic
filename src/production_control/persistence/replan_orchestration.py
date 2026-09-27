"""Connect persisted Live Forecast risk to the pure replanning orchestrator."""

from production_control.core.pace_scheduler_adapter import ForecastReadiness
from production_control.core.replan_orchestrator import (
    CandidateBuilder,
    ReplanOrchestrationResult,
    orchestrate_replan,
)
from production_control.persistence.forecast_result import PersistedForecastResult


def orchestrate_persisted_forecast(
    *,
    forecast: PersistedForecastResult,
    candidate_builder: CandidateBuilder | None = None,
) -> ReplanOrchestrationResult:
    """Run the V1 replanning boundary for one completed Live Forecast result."""

    if forecast.readiness is not ForecastReadiness.READY:
        missing = ", ".join(forecast.missing_gate_ids) or "unknown Forecast inputs"
        raise ValueError(
            "replanning requires READY Live Forecast; unresolved: "
            f"{missing}"
        )

    return orchestrate_replan(
        risk_levels=(summary.risk_level for summary in forecast.lot_forecasts),
        candidate_builder=candidate_builder,
    )
