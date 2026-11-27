"""Derive shop-floor work orders from the current approved plan.

A work order is an operation that the approved plan's Live Forecast starts at
the requested reference time. Because work orders come from the same
event-driven schedule that produces the Forecast, the shop floor executes the
order the plan was evaluated with: approving a new plan changes the next work
orders, which is what closes the loop between replanning and execution.
"""

from dataclasses import dataclass
from datetime import datetime

from sqlalchemy.orm import Session

from production_control.core.pace_scheduler_adapter import ForecastReadiness
from production_control.domain.enums import OperationState
from production_control.persistence.live_forecast import (
    LiveForecastConfig,
    build_live_forecast,
)
from production_control.persistence.models import (
    ResourceRow,
    RoutingStepResourceRow,
    UnitOperationRow,
    UnitRow,
    WorkAttemptRow,
)


@dataclass(frozen=True, slots=True)
class WorkOrder:
    unit_operation_id: str
    attempt_id: str
    lot_id: str
    unit_id: str
    unit_code: str
    process_code: str
    routing_step_id: str
    resource_codes: tuple[str, ...]
    planned_start: datetime
    planned_end: datetime


@dataclass(frozen=True, slots=True)
class WorkOrderSnapshot:
    plan_id: str
    plan_version: int
    as_of: datetime
    readiness: ForecastReadiness
    orders: tuple[WorkOrder, ...]
    waiting_operation_ids: tuple[str, ...]
    # Earliest later start of a not-yet-started operation in the same plan
    # Forecast; lets an idle shop floor know when the next order is due.
    next_start_at: datetime | None = None


def _resource_codes(session: Session, routing_step_id: str) -> tuple[str, ...]:
    rows = (
        session.query(ResourceRow.resource_code)
        .join(
            RoutingStepResourceRow,
            RoutingStepResourceRow.resource_id == ResourceRow.resource_id,
        )
        .filter(RoutingStepResourceRow.routing_step_id == routing_step_id)
        .order_by(ResourceRow.resource_code)
        .all()
    )
    return tuple(row[0] for row in rows)


def build_work_orders(
    *,
    session: Session,
    as_of: datetime,
    config: LiveForecastConfig,
) -> WorkOrderSnapshot:
    """Return the WAITING operations the approved plan starts exactly at ``as_of``.

    RUNNING work continues and is not re-ordered. HOLD work resumes on the
    worker's RESUME event, not on a work order. When the Forecast is WAIT the
    worker must first supply expected remaining time, so no order is issued.
    """

    live = build_live_forecast(session=session, as_of=as_of, config=config)
    if live.readiness is not ForecastReadiness.READY or live.schedule is None:
        return WorkOrderSnapshot(
            plan_id=live.plan_id,
            plan_version=live.plan_version,
            as_of=as_of,
            readiness=live.readiness,
            orders=(),
            waiting_operation_ids=live.waiting_operation_ids,
        )

    orders: list[WorkOrder] = []
    next_start_at: datetime | None = None
    for scheduled in live.schedule.operations:
        if scheduled.start > as_of:
            if next_start_at is None or scheduled.start < next_start_at:
                attempt = session.get(WorkAttemptRow, scheduled.operation_id)
                operation = (
                    None
                    if attempt is None
                    else session.get(UnitOperationRow, attempt.unit_operation_id)
                )
                if operation is not None and operation.state == OperationState.WAITING.value:
                    next_start_at = scheduled.start
            continue
        if scheduled.start != as_of:
            continue
        attempt = session.get(WorkAttemptRow, scheduled.operation_id)
        if attempt is None:
            # Calculation-only work (a projected retest) becomes orderable
            # once the server stages its Attempt.
            continue
        operation = session.get(UnitOperationRow, attempt.unit_operation_id)
        if operation is None:
            raise ValueError(
                f"WorkAttempt references missing UnitOperation: {attempt.unit_operation_id}"
            )
        if operation.state != OperationState.WAITING.value:
            continue
        unit = session.get(UnitRow, operation.unit_id)
        orders.append(
            WorkOrder(
                unit_operation_id=operation.unit_operation_id,
                attempt_id=attempt.attempt_id,
                lot_id=scheduled.lot_id,
                unit_id=scheduled.unit_id,
                unit_code=unit.unit_code if unit is not None else scheduled.unit_id,
                process_code=scheduled.process_code,
                routing_step_id=operation.routing_step_id,
                resource_codes=_resource_codes(session, operation.routing_step_id),
                planned_start=scheduled.start,
                planned_end=scheduled.end,
            )
        )

    return WorkOrderSnapshot(
        plan_id=live.plan_id,
        plan_version=live.plan_version,
        as_of=as_of,
        readiness=live.readiness,
        orders=tuple(orders),
        waiting_operation_ids=(),
        next_start_at=next_start_at,
    )
