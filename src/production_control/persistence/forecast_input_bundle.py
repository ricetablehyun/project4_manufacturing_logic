"""Assemble persisted internal execution state into scheduler inputs.

This is the persistence-side state builder for UNIT_TIME work. It combines
normal current Attempts with D048/D049 rework projection while keeping external
LOT_LEAD_TIME barriers outside this adapter.
"""

from collections.abc import Mapping
from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.orm import Session

from production_control.core.event_scheduler import EventDispatchInput
from production_control.core.pace_estimator import PaceForecast
from production_control.core.pace_scheduler_adapter import (
    ForecastReadiness,
    UnitPaceSchedulingInput,
    UnitPaceSignal,
    build_pace_schedule_inputs,
)
from production_control.persistence.execution_projection import (
    UnitExecutionProjection,
    project_unit_execution_order,
)
from production_control.persistence.models import (
    LotRow,
    RoutingStepRow,
    UnitOperationRow,
    UnitRow,
    WorkAttemptRow,
)
from production_control.persistence.rework_scheduler_adapter import (
    build_waiting_rework_schedule_inputs,
    load_routing_step_requirements,
)


@dataclass(frozen=True, slots=True)
class PersistedForecastInputBundle:
    """Scheduler-ready internal work or an explicit Forecast WAIT state."""

    readiness: ForecastReadiness
    items: tuple[EventDispatchInput, ...]
    waiting_operation_ids: tuple[str, ...]
    signals: tuple[UnitPaceSignal, ...]


def _normal_input_from_projection(
    *,
    session: Session,
    lot: LotRow,
    unit: UnitRow,
    projection: UnitExecutionProjection,
) -> tuple[UnitPaceSchedulingInput, ...]:
    inputs: list[UnitPaceSchedulingInput] = []

    for projected in projection.scheduler_current_attempts:
        if projected.rework_role is not None:
            continue

        operation = session.get(
            UnitOperationRow,
            projected.unit_operation_id,
        )
        if operation is None:
            raise ValueError(
                "projection references missing UnitOperation: "
                f"{projected.unit_operation_id}"
            )
        attempt = session.get(WorkAttemptRow, projected.attempt_id)
        if attempt is None:
            raise ValueError(
                f"projection references missing WorkAttempt: {projected.attempt_id}"
            )
        step = session.get(RoutingStepRow, operation.routing_step_id)
        if step is None:
            raise ValueError(
                "UnitOperation references missing RoutingStep: "
                f"{operation.routing_step_id}"
            )
        if step.duration_mode != "UNIT_TIME":
            raise ValueError(
                "persisted internal forecast bundle only accepts UNIT_TIME steps"
            )
        if step.standard_minutes is None:
            raise ValueError(
                f"UNIT_TIME step is missing standard_minutes: {step.routing_step_id}"
            )

        inputs.append(
            UnitPaceSchedulingInput(
                operation_id=attempt.attempt_id,
                lot_id=lot.lot_id,
                unit_id=unit.unit_id,
                step_seq=projected.step_seq,
                process_code=projected.process_code,
                state=projected.operation_state,
                eligible_at=operation.eligible_at,
                release_at=max(lot.release_at, operation.eligible_at),
                requirements=load_routing_step_requirements(
                    session,
                    routing_step_id=step.routing_step_id,
                ),
                release_buffer_k=step.release_buffer_k,
                active_minutes=attempt.active_minutes,
                hold_remaining_minutes=operation.hold_remaining_minutes,
                standard_minutes_per_unit=step.standard_minutes,
                execution_seq=projected.execution_seq,
            )
        )

    return tuple(inputs)


def _group_normal_inputs(
    inputs: tuple[UnitPaceSchedulingInput, ...],
) -> dict[tuple[str, int], list[UnitPaceSchedulingInput]]:
    grouped: dict[tuple[str, int], list[UnitPaceSchedulingInput]] = {}
    for item in inputs:
        grouped.setdefault(
            (item.process_code, item.step_seq),
            [],
        ).append(item)
    return grouped


def build_internal_lot_forecast_inputs(
    *,
    session: Session,
    lot_id: str,
    pace_by_process: Mapping[str, PaceForecast],
) -> PersistedForecastInputBundle:
    """Build all current internal scheduler inputs for one persisted LOT.

    Normal work is adapted in LOT x process groups so the existing rolling Pace
    workload distribution is preserved. Rework/retest Attempts are added as
    distinct scheduler operations using D048 execution order and D049 duration.
    """

    lot = session.get(LotRow, lot_id)
    if lot is None:
        raise ValueError(f"unknown lot_id: {lot_id}")

    units = session.scalars(
        select(UnitRow)
        .where(UnitRow.lot_id == lot_id)
        .order_by(UnitRow.unit_id)
    ).all()
    if not units:
        raise ValueError(f"LOT has no Units: {lot_id}")

    projections: list[UnitExecutionProjection] = []
    normal_inputs: list[UnitPaceSchedulingInput] = []

    for unit in units:
        projection = project_unit_execution_order(
            session=session,
            unit_id=unit.unit_id,
        )
        projections.append(projection)
        normal_inputs.extend(
            _normal_input_from_projection(
                session=session,
                lot=lot,
                unit=unit,
                projection=projection,
            )
        )

    normal_items: list[EventDispatchInput] = []
    signals: list[UnitPaceSignal] = []
    waiting_operation_ids: list[str] = []

    for (process_code, _step_seq), group in sorted(
        _group_normal_inputs(tuple(normal_inputs)).items()
    ):
        forecast = pace_by_process.get(process_code)
        if forecast is None:
            raise ValueError(
                "missing current LOT x process Pace for normal process: "
                f"{process_code}"
            )
        adapted = build_pace_schedule_inputs(
            forecast=forecast,
            units=tuple(group),
        )
        signals.extend(adapted.signals)
        waiting_operation_ids.extend(adapted.waiting_operation_ids)
        if adapted.readiness is ForecastReadiness.READY:
            normal_items.extend(adapted.items)

    if waiting_operation_ids:
        return PersistedForecastInputBundle(
            readiness=ForecastReadiness.WAIT,
            items=(),
            waiting_operation_ids=tuple(sorted(set(waiting_operation_ids))),
            signals=tuple(signals),
        )

    rework_items: list[EventDispatchInput] = []
    for projection in projections:
        rework_items.extend(
            build_waiting_rework_schedule_inputs(
                session=session,
                projection=projection,
                pace_by_process=pace_by_process,
            )
        )

    items = tuple(
        sorted(
            (*normal_items, *rework_items),
            key=lambda item: (
                item.operation.execution_seq or item.operation.step_seq,
                item.operation.unit_id,
                item.operation.operation_id,
            ),
        )
    )
    operation_ids = [item.operation.operation_id for item in items]
    if len(operation_ids) != len(set(operation_ids)):
        raise ValueError("forecast input bundle contains duplicate operation_id")

    return PersistedForecastInputBundle(
        readiness=ForecastReadiness.READY,
        items=items,
        waiting_operation_ids=(),
        signals=tuple(signals),
    )
