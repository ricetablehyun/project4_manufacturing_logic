"""Build scheduler inputs for newly staged WAITING rework Attempts.

D049: a rework/retest duration uses the current LOT x process Pace. The Pace
object already falls back to the RoutingStep standard until enough completed
samples exist.
"""

from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from production_control.core.dispatch_builder import OperationDispatchInput
from production_control.core.event_scheduler import EventDispatchInput
from production_control.core.finite_scheduler import OperationSpec
from production_control.core.pace_estimator import PaceForecast
from production_control.core.rework_core import ReworkRole
from production_control.core.slot_engine import ResourceRequirement
from production_control.domain.enums import OperationState
from production_control.persistence.execution_projection import (
    UnitExecutionProjection,
)
from production_control.persistence.models import (
    ProcessRow,
    ResourceRow,
    RoutingStepResourceRow,
    RoutingStepRow,
    UnitOperationRow,
    UnitRow,
    WorkAttemptRow,
)
from production_control.persistence.pace_snapshot import effective_attempt_active_minutes


def load_routing_step_requirements(
    session: Session,
    *,
    routing_step_id: str,
) -> tuple[ResourceRequirement, ...]:
    rows = session.execute(
        select(
            ResourceRow.resource_code,
            RoutingStepResourceRow.required_qty,
        )
        .join(
            ResourceRow,
            RoutingStepResourceRow.resource_id == ResourceRow.resource_id,
        )
        .where(
            RoutingStepResourceRow.routing_step_id == routing_step_id,
            ResourceRow.active.is_(True),
        )
        .order_by(ResourceRow.resource_code)
    ).all()
    if not rows:
        raise ValueError(
            "RoutingStep requires at least one active Resource: "
            f"{routing_step_id}"
        )

    return tuple(
        ResourceRequirement(
            resource_code=resource_code,
            quantity=required_qty,
        )
        for resource_code, required_qty in rows
    )


def build_waiting_rework_schedule_inputs(
    *,
    session: Session,
    projection: UnitExecutionProjection,
    pace_by_process: Mapping[str, PaceForecast],
) -> tuple[EventDispatchInput, ...]:
    """Map current WAITING rework Attempts into scheduler inputs using Pace."""

    items: list[EventDispatchInput] = []

    for projected in projection.scheduler_current_attempts:
        if projected.rework_role is None:
            continue
        if projected.operation_state is not OperationState.WAITING:
            raise ValueError(
                "D049 adapter only accepts newly staged WAITING rework Attempts; "
                f"{projected.attempt_id} is {projected.operation_state.value}"
            )

        forecast = pace_by_process.get(projected.process_code)
        if forecast is None:
            raise ValueError(
                "missing current LOT x process Pace for rework process: "
                f"{projected.process_code}"
            )

        operation = session.get(
            UnitOperationRow,
            projected.unit_operation_id,
        )
        if operation is None:
            raise ValueError(
                "projection references missing UnitOperation: "
                f"{projected.unit_operation_id}"
            )
        unit = session.get(UnitRow, operation.unit_id)
        if unit is None:
            raise ValueError(
                f"UnitOperation references missing Unit: {operation.unit_id}"
            )
        step = session.get(RoutingStepRow, operation.routing_step_id)
        if step is None:
            raise ValueError(
                "UnitOperation references missing RoutingStep: "
                f"{operation.routing_step_id}"
            )

        requirements = load_routing_step_requirements(
            session,
            routing_step_id=step.routing_step_id,
        )
        scheduler_operation_id = projected.attempt_id
        items.append(
            EventDispatchInput(
                operation=OperationSpec(
                    operation_id=scheduler_operation_id,
                    lot_id=unit.lot_id,
                    unit_id=unit.unit_id,
                    step_seq=projected.step_seq,
                    process_code=projected.process_code,
                    duration_minutes=forecast.pace_minutes_per_unit,
                    requirements=requirements,
                    release_at=operation.eligible_at,
                    release_buffer_k=step.release_buffer_k,
                    execution_seq=projected.execution_seq,
                ),
                dispatch=OperationDispatchInput(
                    operation_id=scheduler_operation_id,
                    lot_id=unit.lot_id,
                    unit_id=unit.unit_id,
                    state=OperationState.WAITING,
                    eligible_at=operation.eligible_at,
                ),
            )
        )

    return tuple(items)


PROJECTED_RETEST_PREFIX = "PROJECTED-RETEST::"


@dataclass(frozen=True, slots=True)
class ReworkScheduleInputs:
    items: tuple[EventDispatchInput, ...]
    waiting_operation_ids: tuple[str, ...]


def _final_test_operation(session: Session, unit_id: str) -> UnitOperationRow:
    operation = session.scalar(
        select(UnitOperationRow)
        .join(RoutingStepRow, UnitOperationRow.routing_step_id == RoutingStepRow.routing_step_id)
        .join(ProcessRow, RoutingStepRow.process_id == ProcessRow.process_id)
        .where(UnitOperationRow.unit_id == unit_id, ProcessRow.process_code == "FINAL_TEST")
    )
    if operation is None:
        raise ValueError(f"Unit has no FINAL_TEST operation for retest projection: {unit_id}")
    return operation


def build_rework_schedule_inputs(
    *,
    session: Session,
    projection: UnitExecutionProjection,
    pace_by_process: Mapping[str, PaceForecast],
    as_of: datetime | None,
) -> ReworkScheduleInputs:
    """Scheduler inputs for every unfinished rework step of one Unit (D049/D077).

    - WAITING rework Attempt: current Pace (D049, unchanged).
    - RUNNING rework Attempt (D077): Pace minus elapsed active time; once Pace
      is exceeded the worker's expected remaining time is required, exactly
      like normal work (D042/D043).
    - Tuning rework not yet followed by a staged retest (D077): the retest
      Attempt is only persisted when tuning rework completes, but the Unit's
      shipping-inspection Gate depends on it. A calculation-only retest at
      the current FINAL_TEST Pace is projected after the tuning rework so the
      Gate stays forecastable while rework is pending.
    """

    waiting_items = build_waiting_rework_schedule_inputs(
        session=session,
        projection=_with_states(projection, OperationState.WAITING),
        pace_by_process=pace_by_process,
    )
    items: list[EventDispatchInput] = list(waiting_items)
    waiting_operation_ids: list[str] = []
    pending_tuning_rework: list = []

    for projected in projection.scheduler_current_attempts:
        if projected.rework_role is None:
            continue
        if projected.operation_state is OperationState.HOLD:
            raise ValueError(
                f"HOLD rework Attempts are not supported by Forecast: {projected.attempt_id}"
            )
        if projected.rework_role == ReworkRole.TUNING_REWORK.value:
            pending_tuning_rework.append(projected)
        if projected.operation_state is not OperationState.RUNNING:
            continue

        forecast = pace_by_process.get(projected.process_code)
        if forecast is None:
            raise ValueError(
                "missing current LOT x process Pace for rework process: "
                f"{projected.process_code}"
            )
        operation = session.get(UnitOperationRow, projected.unit_operation_id)
        attempt = session.get(WorkAttemptRow, projected.attempt_id)
        if operation is None or attempt is None:
            raise ValueError(f"projection references missing rework rows: {projected.attempt_id}")
        active = float(attempt.active_minutes)
        if as_of is not None:
            active = effective_attempt_active_minutes(
                session=session,
                attempt=attempt,
                operation_state=OperationState.RUNNING,
                as_of=as_of,
            )
        remaining = forecast.pace_minutes_per_unit - active
        if remaining <= 0:
            if operation.expected_remaining_minutes is None:
                waiting_operation_ids.append(projected.attempt_id)
                continue
            remaining = float(operation.expected_remaining_minutes)
        unit = session.get(UnitRow, operation.unit_id)
        step = session.get(RoutingStepRow, operation.routing_step_id)
        if unit is None or step is None:
            raise ValueError(
                f"rework operation references missing rows: {operation.unit_operation_id}"
            )
        items.append(
            EventDispatchInput(
                operation=OperationSpec(
                    operation_id=projected.attempt_id,
                    lot_id=unit.lot_id,
                    unit_id=unit.unit_id,
                    step_seq=projected.step_seq,
                    process_code=projected.process_code,
                    duration_minutes=remaining,
                    requirements=load_routing_step_requirements(
                        session, routing_step_id=step.routing_step_id
                    ),
                    release_at=operation.eligible_at,
                    release_buffer_k=None,
                    execution_seq=projected.execution_seq,
                ),
                dispatch=OperationDispatchInput(
                    operation_id=projected.attempt_id,
                    lot_id=unit.lot_id,
                    unit_id=unit.unit_id,
                    state=OperationState.RUNNING,
                    eligible_at=operation.eligible_at,
                ),
            )
        )

    for tuning in pending_tuning_rework:
        final_test = _final_test_operation(session, projection.unit_id)
        forecast = pace_by_process.get("FINAL_TEST")
        if forecast is None:
            raise ValueError("missing current LOT x process Pace for rework process: FINAL_TEST")
        unit = session.get(UnitRow, final_test.unit_id)
        tuning_operation = session.get(UnitOperationRow, tuning.unit_operation_id)
        step = session.get(RoutingStepRow, final_test.routing_step_id)
        if unit is None or tuning_operation is None or step is None:
            raise ValueError(f"retest projection references missing rows: {projection.unit_id}")
        operation_id = f"{PROJECTED_RETEST_PREFIX}{final_test.unit_operation_id}"
        execution_seq = max(attempt.execution_seq for attempt in projection.attempts) + 1
        items.append(
            EventDispatchInput(
                operation=OperationSpec(
                    operation_id=operation_id,
                    lot_id=unit.lot_id,
                    unit_id=unit.unit_id,
                    step_seq=step.seq_no,
                    process_code="FINAL_TEST",
                    duration_minutes=forecast.pace_minutes_per_unit,
                    requirements=load_routing_step_requirements(
                        session, routing_step_id=step.routing_step_id
                    ),
                    release_at=tuning_operation.eligible_at,
                    release_buffer_k=None,
                    execution_seq=execution_seq,
                ),
                dispatch=OperationDispatchInput(
                    operation_id=operation_id,
                    lot_id=unit.lot_id,
                    unit_id=unit.unit_id,
                    state=OperationState.WAITING,
                    eligible_at=tuning_operation.eligible_at,
                ),
            )
        )

    return ReworkScheduleInputs(
        items=tuple(items),
        waiting_operation_ids=tuple(waiting_operation_ids),
    )


def _with_states(
    projection: UnitExecutionProjection,
    state: OperationState,
) -> UnitExecutionProjection:
    """Projection view whose current rework Attempts are only in ``state``."""

    return UnitExecutionProjection(
        unit_id=projection.unit_id,
        attempts=tuple(
            attempt
            for attempt in projection.attempts
            if attempt.rework_role is None
            or not attempt.is_current
            or attempt.operation_state is state
            or attempt.operation_state is OperationState.COMPLETED
        ),
    )
