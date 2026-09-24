"""Build scheduler inputs for newly staged WAITING rework Attempts.

D049: a rework/retest duration uses the current LOT x process Pace. The Pace
object already falls back to the RoutingStep standard until enough completed
samples exist.
"""

from collections.abc import Mapping

from sqlalchemy import select
from sqlalchemy.orm import Session

from production_control.core.dispatch_builder import OperationDispatchInput
from production_control.core.event_scheduler import EventDispatchInput
from production_control.core.finite_scheduler import OperationSpec
from production_control.core.pace_estimator import PaceForecast
from production_control.core.slot_engine import ResourceRequirement
from production_control.domain.enums import OperationState
from production_control.persistence.execution_projection import (
    UnitExecutionProjection,
)
from production_control.persistence.models import (
    ResourceRow,
    RoutingStepResourceRow,
    RoutingStepRow,
    UnitOperationRow,
    UnitRow,
)


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
