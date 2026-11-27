"""Read-only persisted execution views for operator-facing clients."""

from dataclasses import dataclass
from datetime import datetime

from sqlalchemy import Select, select
from sqlalchemy.orm import Session

from production_control.persistence.models import (
    ProcessRow,
    RoutingStepRow,
    UnitOperationRow,
    UnitRow,
    WorkAttemptRow,
    WorkEventRow,
)


@dataclass(frozen=True, slots=True)
class UnitOperationView:
    operation_id: str
    lot_id: str
    unit_id: str
    unit_code: str
    routing_step_id: str
    seq_no: int
    process_code: str
    state: str
    eligible_at: datetime
    attempt_no: int
    active_minutes: float
    result: str | None
    last_event_at: datetime | None
    expected_remaining_minutes: float | None


def _statement(*, lot_id: str | None) -> Select[tuple[object, ...]]:
    latest_event_at = (
        select(WorkEventRow.occurred_at)
        .where(WorkEventRow.attempt_id == WorkAttemptRow.attempt_id)
        .order_by(WorkEventRow.occurred_at.desc(), WorkEventRow.event_id.desc())
        .limit(1)
        .correlate(WorkAttemptRow)
        .scalar_subquery()
    )

    statement = (
        select(
            UnitOperationRow.unit_operation_id,
            UnitRow.lot_id,
            UnitOperationRow.unit_id,
            UnitRow.unit_code,
            UnitOperationRow.routing_step_id,
            RoutingStepRow.seq_no,
            ProcessRow.process_code,
            UnitOperationRow.state,
            UnitOperationRow.eligible_at,
            UnitOperationRow.current_attempt_no,
            WorkAttemptRow.active_minutes,
            WorkAttemptRow.result,
            latest_event_at.label("last_event_at"),
            UnitOperationRow.expected_remaining_minutes,
        )
        .join(UnitRow, UnitRow.unit_id == UnitOperationRow.unit_id)
        .join(
            RoutingStepRow,
            RoutingStepRow.routing_step_id == UnitOperationRow.routing_step_id,
        )
        .join(ProcessRow, ProcessRow.process_id == RoutingStepRow.process_id)
        .outerjoin(
            WorkAttemptRow,
            (WorkAttemptRow.unit_operation_id == UnitOperationRow.unit_operation_id)
            & (WorkAttemptRow.attempt_no == UnitOperationRow.current_attempt_no),
        )
    )
    if lot_id is not None:
        statement = statement.where(UnitRow.lot_id == lot_id)
    return statement.order_by(UnitRow.lot_id, UnitRow.unit_code, RoutingStepRow.seq_no)


def list_unit_operations(
    *,
    session: Session,
    lot_id: str | None = None,
) -> tuple[UnitOperationView, ...]:
    """Return deterministic current execution rows without mutating state."""

    rows = session.execute(_statement(lot_id=lot_id)).all()
    return tuple(
        UnitOperationView(
            operation_id=row.unit_operation_id,
            lot_id=row.lot_id,
            unit_id=row.unit_id,
            unit_code=row.unit_code,
            routing_step_id=row.routing_step_id,
            seq_no=row.seq_no,
            process_code=row.process_code,
            state=row.state,
            eligible_at=row.eligible_at,
            attempt_no=row.current_attempt_no,
            active_minutes=float(row.active_minutes or 0.0),
            result=row.result,
            last_event_at=row.last_event_at,
            expected_remaining_minutes=row.expected_remaining_minutes,
        )
        for row in rows
    )
