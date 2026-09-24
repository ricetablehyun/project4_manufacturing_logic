"""Materialize persisted Unit execution instances from a confirmed Routing.

Only UNIT_TIME steps become UnitOperation rows. LOT_LEAD_TIME steps stay as
LOT-level barriers, matching the confirmed external-process model.
"""

from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.orm import Session

from production_control.persistence.models import (
    LotRow,
    RoutingRow,
    RoutingStepRow,
    UnitOperationRow,
    UnitRow,
    WorkAttemptRow,
)


@dataclass(frozen=True, slots=True)
class MaterializationResult:
    lot_id: str
    created_operations: int
    created_attempts: int
    existing_operations: int
    existing_attempts: int


def _operation_id(unit_id: str, routing_step_id: str) -> str:
    return f"OP::{unit_id}::{routing_step_id}"


def _attempt_id(operation_id: str, attempt_no: int) -> str:
    return f"ATTEMPT::{operation_id}::{attempt_no}"


def _load_active_routing(session: Session, product_id: str) -> RoutingRow:
    routings = session.scalars(
        select(RoutingRow)
        .where(
            RoutingRow.product_id == product_id,
            RoutingRow.active.is_(True),
        )
        .order_by(RoutingRow.version)
    ).all()
    if len(routings) != 1:
        raise ValueError(
            "materialization requires exactly one active Routing for product "
            f"{product_id}; found {len(routings)}"
        )
    return routings[0]


def materialize_lot_execution(
    *,
    session: Session,
    lot_id: str,
) -> MaterializationResult:
    """Create one UnitOperation + initial WorkAttempt for each internal Unit step.

    The operation's initial eligible_at uses the LOT release timestamp as its
    earliest release. Routing precedence and external LOT barriers remain
    separate constraints and are not flattened into this timestamp.
    """

    lot = session.get(LotRow, lot_id)
    if lot is None:
        raise ValueError(f"unknown lot_id: {lot_id}")

    routing = _load_active_routing(session, lot.product_id)
    units = session.scalars(
        select(UnitRow)
        .where(UnitRow.lot_id == lot_id)
        .order_by(UnitRow.unit_id)
    ).all()
    internal_steps = session.scalars(
        select(RoutingStepRow)
        .where(
            RoutingStepRow.routing_id == routing.routing_id,
            RoutingStepRow.duration_mode == "UNIT_TIME",
        )
        .order_by(RoutingStepRow.seq_no, RoutingStepRow.routing_step_id)
    ).all()

    created_operations = 0
    created_attempts = 0
    existing_operations = 0
    existing_attempts = 0

    for unit in units:
        for step in internal_steps:
            operation_id = _operation_id(unit.unit_id, step.routing_step_id)
            operation = session.get(UnitOperationRow, operation_id)
            if operation is None:
                operation = UnitOperationRow(
                    unit_operation_id=operation_id,
                    unit_id=unit.unit_id,
                    routing_step_id=step.routing_step_id,
                    state="WAITING",
                    eligible_at=lot.release_at,
                    current_attempt_no=1,
                )
                session.add(operation)
                session.flush()
                created_operations += 1
            else:
                existing_operations += 1

            attempt_id = _attempt_id(operation_id, 1)
            attempt = session.get(WorkAttemptRow, attempt_id)
            if attempt is None:
                session.add(
                    WorkAttemptRow(
                        attempt_id=attempt_id,
                        unit_operation_id=operation_id,
                        attempt_no=1,
                        active_minutes=0,
                    )
                )
                created_attempts += 1
            else:
                existing_attempts += 1

    session.commit()
    return MaterializationResult(
        lot_id=lot_id,
        created_operations=created_operations,
        created_attempts=created_attempts,
        existing_operations=existing_operations,
        existing_attempts=existing_attempts,
    )
