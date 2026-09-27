"""Build user-facing LOT/process Forecast and Gate risk from a schedule result.

The scheduler stays persistence-agnostic. This module joins its temporary
Unit/Attempt schedule back to persisted InspectionGate and RoutingStep data.
"""

from dataclasses import dataclass
from datetime import datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from production_control.core.finite_scheduler import (
    LotProcessForecast,
    ScheduledOperation,
    ScheduleResult,
    aggregate_lot_process_forecast,
)
from production_control.core.pace_scheduler_adapter import ForecastReadiness
from production_control.core.risk_engine import (
    GateRisk,
    RiskLevel,
    evaluate_gate_risk,
    lot_risk_level,
)
from production_control.domain.enums import OperationState
from production_control.persistence.external_step_barrier import (
    ExternalStepBarrier,
    load_lot_external_barriers,
)
from production_control.persistence.models import (
    InspectionGateRow,
    LotRow,
    ProcessRow,
    RoutingStepRow,
    UnitOperationRow,
    UnitRow,
    WorkAttemptRow,
)


@dataclass(frozen=True, slots=True)
class PersistedGateForecast:
    gate_id: str
    lot_id: str
    required_after_step_id: str
    gate_type: str
    forecast_at: datetime
    risk: GateRisk


@dataclass(frozen=True, slots=True)
class LotForecastSummary:
    lot_id: str
    forecast_end: datetime
    risk_level: RiskLevel


@dataclass(frozen=True, slots=True)
class PersistedForecastResult:
    readiness: ForecastReadiness
    process_forecasts: tuple[LotProcessForecast, ...]
    gate_forecasts: tuple[PersistedGateForecast, ...]
    lot_forecasts: tuple[LotForecastSummary, ...]
    missing_gate_ids: tuple[str, ...]
    external_barriers: tuple[ExternalStepBarrier, ...]


def _load_pending_gates(
    session: Session,
    *,
    lot_ids: tuple[str, ...],
) -> tuple[InspectionGateRow, ...]:
    if not lot_ids:
        return ()
    rows = session.scalars(
        select(InspectionGateRow)
        .where(
            InspectionGateRow.lot_id.in_(lot_ids),
            InspectionGateRow.completed_at.is_(None),
        )
        .order_by(
            InspectionGateRow.lot_id,
            InspectionGateRow.planned_at,
            InspectionGateRow.gate_id,
        )
    ).all()
    return tuple(rows)


def _scheduled_required_step_ends(
    *,
    schedule: ScheduleResult,
    lot_id: str,
    step_seq: int,
) -> tuple[ScheduledOperation, ...]:
    return tuple(
        operation
        for operation in schedule.operations
        if operation.lot_id == lot_id and operation.step_seq == step_seq
    )


def _actual_completed_unit_ends(
    *,
    session: Session,
    lot_id: str,
    step: RoutingStepRow,
    process: ProcessRow,
) -> dict[str, datetime]:
    rows = session.execute(
        select(UnitOperationRow, UnitRow)
        .join(UnitRow, UnitOperationRow.unit_id == UnitRow.unit_id)
        .where(
            UnitRow.lot_id == lot_id,
            UnitOperationRow.routing_step_id == step.routing_step_id,
        )
        .order_by(UnitRow.unit_id)
    ).all()

    completed: dict[str, datetime] = {}
    for operation, unit in rows:
        if operation.state != OperationState.COMPLETED.value:
            continue
        attempt = session.scalar(
            select(WorkAttemptRow).where(
                WorkAttemptRow.unit_operation_id == operation.unit_operation_id,
                WorkAttemptRow.attempt_no == operation.current_attempt_no,
            )
        )
        if attempt is None or attempt.ended_at is None:
            continue
        # FINAL_TEST must have an accepted PASS result before it can satisfy
        # a Gate. COMPLETE alone or FAIL keeps the Gate requirement unresolved.
        if process.process_code == "FINAL_TEST" and attempt.result != "PASS":
            continue
        completed[unit.unit_id] = attempt.ended_at
    return completed


def _forecast_internal_step_completion(
    *,
    session: Session,
    schedule: ScheduleResult,
    lot_id: str,
    step: RoutingStepRow,
    process: ProcessRow,
) -> datetime | None:
    unit_ids = tuple(
        session.scalars(
            select(UnitRow.unit_id)
            .where(UnitRow.lot_id == lot_id)
            .order_by(UnitRow.unit_id)
        ).all()
    )
    if not unit_ids:
        return None

    actual_by_unit = _actual_completed_unit_ends(
        session=session,
        lot_id=lot_id,
        step=step,
        process=process,
    )
    scheduled = _scheduled_required_step_ends(
        schedule=schedule,
        lot_id=lot_id,
        step_seq=step.seq_no,
    )
    scheduled_by_unit: dict[str, datetime] = {}
    for operation in scheduled:
        previous = scheduled_by_unit.get(operation.unit_id)
        if previous is None or operation.end > previous:
            scheduled_by_unit[operation.unit_id] = operation.end

    covered = set(actual_by_unit) | set(scheduled_by_unit)
    if set(unit_ids) - covered:
        return None

    return max((*actual_by_unit.values(), *scheduled_by_unit.values()))


def _forecast_gate_requirement(
    *,
    session: Session,
    schedule: ScheduleResult,
    gate: InspectionGateRow,
    external_barriers: tuple[ExternalStepBarrier, ...],
) -> datetime | None:
    step = session.get(RoutingStepRow, gate.required_after_step_id)
    if step is None:
        raise ValueError(
            "InspectionGate references missing RoutingStep: "
            f"{gate.required_after_step_id}"
        )
    process = session.get(ProcessRow, step.process_id)
    if process is None:
        raise ValueError(f"RoutingStep references missing Process: {step.process_id}")

    if step.duration_mode == "LOT_LEAD_TIME":
        barrier = next(
            (
                candidate
                for candidate in external_barriers
                if candidate.lot_id == gate.lot_id
                and candidate.routing_step_id == step.routing_step_id
            ),
            None,
        )
        return None if barrier is None else barrier.finish_at

    if step.duration_mode == "UNIT_TIME":
        return _forecast_internal_step_completion(
            session=session,
            schedule=schedule,
            lot_id=gate.lot_id,
            step=step,
            process=process,
        )

    return None


def evaluate_persisted_forecast(
    *,
    session: Session,
    schedule: ScheduleResult,
    lot_ids: tuple[str, ...],
    warning_threshold_minutes: float,
) -> PersistedForecastResult:
    """Aggregate one temporary schedule and evaluate all pending persisted Gates."""

    if len(lot_ids) != len(set(lot_ids)):
        raise ValueError("lot_ids must not contain duplicates")
    if not lot_ids:
        return PersistedForecastResult(
            readiness=ForecastReadiness.READY,
            process_forecasts=(),
            gate_forecasts=(),
            lot_forecasts=(),
            missing_gate_ids=(),
            external_barriers=(),
        )

    for lot_id in lot_ids:
        if session.get(LotRow, lot_id) is None:
            raise ValueError(f"unknown lot_id: {lot_id}")

    selected_lot_ids = set(lot_ids)
    process_forecasts = tuple(
        forecast
        for forecast in aggregate_lot_process_forecast(schedule.operations)
        if forecast.lot_id in selected_lot_ids
    )

    external_barriers: list[ExternalStepBarrier] = []
    for lot_id in lot_ids:
        barriers, _missing = load_lot_external_barriers(
            session=session,
            lot_id=lot_id,
        )
        external_barriers.extend(barriers)
    barrier_tuple = tuple(external_barriers)

    gate_forecasts: list[PersistedGateForecast] = []
    missing_gate_ids: list[str] = []
    for gate in _load_pending_gates(session, lot_ids=lot_ids):
        forecast_at = _forecast_gate_requirement(
            session=session,
            schedule=schedule,
            gate=gate,
            external_barriers=barrier_tuple,
        )
        if forecast_at is None:
            missing_gate_ids.append(gate.gate_id)
            continue
        risk = evaluate_gate_risk(
            gate_id=gate.gate_id,
            planned_at=gate.planned_at,
            forecast_at=forecast_at,
            warning_threshold_minutes=warning_threshold_minutes,
        )
        gate_forecasts.append(
            PersistedGateForecast(
                gate_id=gate.gate_id,
                lot_id=gate.lot_id,
                required_after_step_id=gate.required_after_step_id,
                gate_type=gate.gate_type,
                forecast_at=forecast_at,
                risk=risk,
            )
        )

    lot_forecasts: list[LotForecastSummary] = []
    for lot_id in lot_ids:
        operation_ends = [
            operation.end
            for operation in schedule.operations
            if operation.lot_id == lot_id
        ]
        barrier_ends = [
            barrier.finish_at
            for barrier in barrier_tuple
            if barrier.lot_id == lot_id
        ]
        forecast_ends = (*operation_ends, *barrier_ends)
        if not forecast_ends:
            continue
        lot_gate_risks = tuple(
            gate_forecast.risk
            for gate_forecast in gate_forecasts
            if gate_forecast.lot_id == lot_id
        )
        lot_forecasts.append(
            LotForecastSummary(
                lot_id=lot_id,
                forecast_end=max(forecast_ends),
                risk_level=lot_risk_level(lot_gate_risks),
            )
        )

    return PersistedForecastResult(
        readiness=(
            ForecastReadiness.WAIT
            if missing_gate_ids
            else ForecastReadiness.READY
        ),
        process_forecasts=process_forecasts,
        gate_forecasts=tuple(gate_forecasts),
        lot_forecasts=tuple(lot_forecasts),
        missing_gate_ids=tuple(missing_gate_ids),
        external_barriers=barrier_tuple,
    )
