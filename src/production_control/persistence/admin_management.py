"""Safe LOT / InspectionGate management for the administrator API.

D059 intentionally exposes only existing-entity lookup and a narrow set of
mutable schedule/status fields. Structural identity and materialized quantity
remain outside this service.
"""

from datetime import datetime
from typing import Final

from sqlalchemy import select
from sqlalchemy.orm import Session

from production_control.persistence.models import InspectionGateRow, LotRow

_UNSET: Final = object()


def list_lots(*, session: Session) -> tuple[LotRow, ...]:
    """Return LOT rows in stable identifier order."""

    return tuple(
        session.scalars(select(LotRow).order_by(LotRow.lot_id)).all()
    )


def update_lot(
    *,
    session: Session,
    lot_id: str,
    release_at: datetime | object = _UNSET,
    due_at: datetime | object = _UNSET,
    status: str | object = _UNSET,
) -> LotRow:
    """Update only D059-approved mutable LOT fields."""

    row = session.get(LotRow, lot_id)
    if row is None:
        raise LookupError(f"unknown lot_id: {lot_id}")

    if release_at is not _UNSET:
        row.release_at = release_at  # type: ignore[assignment]
    if due_at is not _UNSET:
        row.due_at = due_at  # type: ignore[assignment]
    if status is not _UNSET:
        row.status = status  # type: ignore[assignment]

    session.commit()
    session.refresh(row)
    return row


def list_inspection_gates(
    *,
    session: Session,
    lot_id: str | None = None,
) -> tuple[InspectionGateRow, ...]:
    """Return inspection gates, optionally scoped to one LOT."""

    statement = select(InspectionGateRow)
    if lot_id is not None:
        statement = statement.where(InspectionGateRow.lot_id == lot_id)
    statement = statement.order_by(InspectionGateRow.gate_id)
    return tuple(session.scalars(statement).all())


def update_inspection_gate(
    *,
    session: Session,
    gate_id: str,
    planned_at: datetime | object = _UNSET,
    completed_at: datetime | None | object = _UNSET,
    status: str | object = _UNSET,
) -> InspectionGateRow:
    """Update only D059-approved mutable InspectionGate fields."""

    row = session.get(InspectionGateRow, gate_id)
    if row is None:
        raise LookupError(f"unknown gate_id: {gate_id}")

    if planned_at is not _UNSET:
        row.planned_at = planned_at  # type: ignore[assignment]
    if completed_at is not _UNSET:
        row.completed_at = completed_at  # type: ignore[assignment]
    if status is not _UNSET:
        row.status = status  # type: ignore[assignment]

    session.commit()
    session.refresh(row)
    return row
