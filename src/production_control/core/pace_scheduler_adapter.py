"""Adapt LOT x process Pace forecasts into event-scheduler inputs.

This adapter implements the confirmed V1 boundary:
- D040/D044: rolling remaining normal work is distributed equally across
  unfinished normal Units.
- D042: a RUNNING Unit that has exceeded the current Pace uses the worker's
  expected remaining minutes as its future residual workload.
- D043: if that worker estimate is missing, Forecast stays WAIT/UNKNOWN and no
  scheduler inputs are emitted.
- D031/D034: HOLD uses a manager-entered remaining-time override when present;
  otherwise it falls back to the RoutingStep standard time and exposes that
  fallback basis for the UI.

The adapter does not create rework operations. Confirmed rework remains a
separate scheduling input.
"""

from collections.abc import Sequence
from dataclasses import dataclass, replace
from datetime import datetime
from enum import StrEnum
from math import isfinite

from production_control.core.dispatch_builder import OperationDispatchInput
from production_control.core.event_scheduler import EventDispatchInput
from production_control.core.finite_scheduler import OperationSpec
from production_control.core.pace_estimator import PaceForecast
from production_control.core.pace_workload import distribute_remaining_normal_work
from production_control.core.slot_engine import ResourceRequirement
from production_control.domain.enums import OperationState


class ForecastReadiness(StrEnum):
    READY = "READY"
    WAIT = "WAIT"


class HoldDurationBasis(StrEnum):
    """Source used for a HOLD Unit's forecast remaining duration."""

    MANAGER_OVERRIDE = "MANAGER_OVERRIDE"
    STANDARD_FALLBACK = "STANDARD_FALLBACK"


@dataclass(frozen=True, slots=True)
class UnitPaceSchedulingInput:
    """Unfinished normal Unit operation to adapt for scheduling."""

    operation_id: str
    lot_id: str
    unit_id: str
    step_seq: int
    process_code: str
    state: OperationState
    eligible_at: datetime
    release_at: datetime
    requirements: tuple[ResourceRequirement, ...]
    release_buffer_k: int | None = None
    active_minutes: float = 0.0
    expected_remaining_minutes: float | None = None
    hold_remaining_minutes: float | None = None
    standard_minutes_per_unit: float | None = None

    def __post_init__(self) -> None:
        if not self.operation_id:
            raise ValueError("operation_id must not be empty")
        if not self.lot_id:
            raise ValueError("lot_id must not be empty")
        if not self.unit_id:
            raise ValueError("unit_id must not be empty")
        if self.step_seq <= 0:
            raise ValueError("step_seq must be greater than 0")
        if not self.process_code:
            raise ValueError("process_code must not be empty")
        if self.state is OperationState.COMPLETED:
            raise ValueError("completed operations must not enter Pace scheduling")
        if not self.requirements:
            raise ValueError("at least one resource requirement is required")
        if self.active_minutes < 0 or not isfinite(self.active_minutes):
            raise ValueError("active_minutes must be finite and 0 or greater")
        if self.expected_remaining_minutes is not None and (
            self.expected_remaining_minutes <= 0
            or not isfinite(self.expected_remaining_minutes)
        ):
            raise ValueError(
                "expected_remaining_minutes must be finite and greater than 0"
            )
        if self.hold_remaining_minutes is not None and (
            self.hold_remaining_minutes <= 0
            or not isfinite(self.hold_remaining_minutes)
        ):
            raise ValueError(
                "hold_remaining_minutes must be finite and greater than 0"
            )
        if self.standard_minutes_per_unit is not None and (
            self.standard_minutes_per_unit <= 0
            or not isfinite(self.standard_minutes_per_unit)
        ):
            raise ValueError(
                "standard_minutes_per_unit must be finite and greater than 0"
            )


@dataclass(frozen=True, slots=True)
class UnitPaceSignal:
    """Forecast/UI signal for one unfinished Unit."""

    operation_id: str
    unit_id: str
    pace_overrun_minutes: float
    expected_remaining_minutes: float | None
    hold_forecast_minutes: float | None
    hold_duration_basis: HoldDurationBasis | None


@dataclass(frozen=True, slots=True)
class PaceScheduleAdapterResult:
    """Ready scheduler inputs or an explicit Forecast WAIT state."""

    readiness: ForecastReadiness
    items: tuple[EventDispatchInput, ...]
    waiting_operation_ids: tuple[str, ...]
    signals: tuple[UnitPaceSignal, ...]


def _validate_group(units: tuple[UnitPaceSchedulingInput, ...]) -> None:
    if not units:
        return

    operation_ids = [unit.operation_id for unit in units]
    if len(operation_ids) != len(set(operation_ids)):
        raise ValueError("operation_id values must be unique")

    unit_ids = [unit.unit_id for unit in units]
    if len(unit_ids) != len(set(unit_ids)):
        raise ValueError("unit_id values must be unique within one LOT x process")

    lot_ids = {unit.lot_id for unit in units}
    process_codes = {unit.process_code for unit in units}
    step_seqs = {unit.step_seq for unit in units}
    if len(lot_ids) != 1 or len(process_codes) != 1 or len(step_seqs) != 1:
        raise ValueError(
            "adapter input must represent exactly one LOT x process routing step"
        )


def resume_held_unit(
    *,
    unit: UnitPaceSchedulingInput,
    resumed_at: datetime,
) -> UnitPaceSchedulingInput:
    """Return the planning view after an actual HOLD -> RESUME event."""

    if unit.state is not OperationState.HOLD:
        raise ValueError("only HOLD operations can be resumed")

    return replace(
        unit,
        state=OperationState.RUNNING,
        eligible_at=max(unit.eligible_at, resumed_at),
        release_at=max(unit.release_at, resumed_at),
    )


def build_pace_schedule_inputs(
    *,
    forecast: PaceForecast,
    units: Sequence[UnitPaceSchedulingInput],
) -> PaceScheduleAdapterResult:
    """Build event-scheduler inputs from one LOT x process Pace snapshot."""

    unit_tuple = tuple(units)
    _validate_group(unit_tuple)

    if not unit_tuple:
        if forecast.remaining_normal_work_minutes > 0:
            raise ValueError(
                "positive remaining normal work requires unfinished Unit inputs"
            )
        return PaceScheduleAdapterResult(
            readiness=ForecastReadiness.READY,
            items=(),
            waiting_operation_ids=(),
            signals=(),
        )

    chunks = distribute_remaining_normal_work(
        remaining_normal_work_minutes=forecast.remaining_normal_work_minutes,
        unfinished_unit_ids=tuple(unit.unit_id for unit in unit_tuple),
    )
    workload_by_unit = {
        chunk.unit_id: chunk.workload_minutes
        for chunk in chunks
    }

    signals: list[UnitPaceSignal] = []
    waiting_operation_ids: list[str] = []
    duration_by_operation: dict[str, float] = {}

    for unit in unit_tuple:
        pace_overrun = 0.0
        hold_forecast_minutes: float | None = None
        hold_duration_basis: HoldDurationBasis | None = None

        if unit.state is OperationState.RUNNING:
            pace_overrun = max(
                unit.active_minutes - forecast.pace_minutes_per_unit,
                0.0,
            )

        if unit.state is OperationState.HOLD:
            if unit.hold_remaining_minutes is not None:
                hold_forecast_minutes = unit.hold_remaining_minutes
                hold_duration_basis = HoldDurationBasis.MANAGER_OVERRIDE
            elif unit.standard_minutes_per_unit is not None:
                hold_forecast_minutes = unit.standard_minutes_per_unit
                hold_duration_basis = HoldDurationBasis.STANDARD_FALLBACK
            else:
                raise ValueError(
                    "HOLD operation requires hold_remaining_minutes or "
                    "standard_minutes_per_unit"
                )

        signals.append(
            UnitPaceSignal(
                operation_id=unit.operation_id,
                unit_id=unit.unit_id,
                pace_overrun_minutes=pace_overrun,
                expected_remaining_minutes=unit.expected_remaining_minutes,
                hold_forecast_minutes=hold_forecast_minutes,
                hold_duration_basis=hold_duration_basis,
            )
        )

        if unit.state is OperationState.HOLD:
            duration = hold_forecast_minutes
        elif pace_overrun > 0:
            if unit.expected_remaining_minutes is None:
                waiting_operation_ids.append(unit.operation_id)
                continue
            duration = unit.expected_remaining_minutes
        else:
            duration = workload_by_unit[unit.unit_id]

        if duration <= 0:
            waiting_operation_ids.append(unit.operation_id)
            continue

        duration_by_operation[unit.operation_id] = duration

    if waiting_operation_ids:
        return PaceScheduleAdapterResult(
            readiness=ForecastReadiness.WAIT,
            items=(),
            waiting_operation_ids=tuple(waiting_operation_ids),
            signals=tuple(signals),
        )

    items = tuple(
        EventDispatchInput(
            operation=OperationSpec(
                operation_id=unit.operation_id,
                lot_id=unit.lot_id,
                unit_id=unit.unit_id,
                step_seq=unit.step_seq,
                process_code=unit.process_code,
                duration_minutes=duration_by_operation[unit.operation_id],
                requirements=unit.requirements,
                release_at=unit.release_at,
                release_buffer_k=unit.release_buffer_k,
            ),
            dispatch=OperationDispatchInput(
                operation_id=unit.operation_id,
                lot_id=unit.lot_id,
                unit_id=unit.unit_id,
                state=unit.state,
                eligible_at=unit.eligible_at,
            ),
        )
        for unit in unit_tuple
    )

    return PaceScheduleAdapterResult(
        readiness=ForecastReadiness.READY,
        items=items,
        waiting_operation_ids=(),
        signals=tuple(signals),
    )
