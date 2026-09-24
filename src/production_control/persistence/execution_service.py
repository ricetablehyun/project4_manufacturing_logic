"""Transactional WorkEvent persistence backed by the pure execution-state core."""

from datetime import datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from production_control.core.execution_state import (
    AttemptResult,
    OperationExecutionSnapshot,
    WorkEventApplyResult,
    WorkEventInput,
    WorkEventType,
    apply_work_event,
)
from production_control.domain.enums import OperationState
from production_control.persistence.models import (
    ProcessRow,
    RoutingStepRow,
    UnitOperationRow,
    UnitRow,
    WorkAttemptRow,
    WorkEventRow,
)


def _load_current_attempt(
    session: Session,
    operation: UnitOperationRow,
) -> WorkAttemptRow:
    attempt = session.scalar(
        select(WorkAttemptRow).where(
            WorkAttemptRow.unit_operation_id == operation.unit_operation_id,
            WorkAttemptRow.attempt_no == operation.current_attempt_no,
        )
    )
    if attempt is None:
        raise ValueError(
            "current WorkAttempt is missing for UnitOperation "
            f"{operation.unit_operation_id}"
        )
    return attempt


def _load_execution_snapshot(
    session: Session,
    unit_operation_id: str,
) -> tuple[UnitOperationRow, WorkAttemptRow, OperationExecutionSnapshot]:
    operation = session.get(UnitOperationRow, unit_operation_id)
    if operation is None:
        raise ValueError(f"unknown unit_operation_id: {unit_operation_id}")

    unit = session.get(UnitRow, operation.unit_id)
    if unit is None:
        raise ValueError(f"UnitOperation references missing Unit: {operation.unit_id}")

    step = session.get(RoutingStepRow, operation.routing_step_id)
    if step is None:
        raise ValueError(
            "UnitOperation references missing RoutingStep: "
            f"{operation.routing_step_id}"
        )

    process = session.get(ProcessRow, step.process_id)
    if process is None:
        raise ValueError(f"RoutingStep references missing Process: {step.process_id}")

    attempt = _load_current_attempt(session, operation)
    events = session.scalars(
        select(WorkEventRow)
        .where(WorkEventRow.attempt_id == attempt.attempt_id)
        .order_by(WorkEventRow.occurred_at, WorkEventRow.event_id)
    ).all()

    state = OperationState(operation.state)
    active_started_at = None
    if state is OperationState.RUNNING:
        for persisted_event in reversed(events):
            if persisted_event.event_type in {
                WorkEventType.START.value,
                WorkEventType.RESUME.value,
            }:
                active_started_at = persisted_event.occurred_at
                break
        if active_started_at is None:
            raise ValueError("RUNNING WorkAttempt has no START/RESUME event")

    last_hold_reason = None
    for persisted_event in reversed(events):
        if persisted_event.event_type == WorkEventType.HOLD.value:
            last_hold_reason = persisted_event.reason
            break

    result = AttemptResult(attempt.result) if attempt.result is not None else None

    snapshot = OperationExecutionSnapshot(
        operation_id=operation.unit_operation_id,
        lot_id=unit.lot_id,
        unit_id=unit.unit_id,
        process_code=process.process_code,
        state=state,
        attempt_no=attempt.attempt_no,
        active_minutes=attempt.active_minutes,
        active_started_at=active_started_at,
        last_event_at=events[-1].occurred_at if events else None,
        result=result,
        last_hold_reason=last_hold_reason,
        seen_event_ids=tuple(row.event_id for row in events),
    )
    return operation, attempt, snapshot


def persist_work_event(
    *,
    session: Session,
    unit_operation_id: str,
    event: WorkEventInput,
    received_at: datetime,
    station_code: str | None = None,
    worker_code: str | None = None,
) -> WorkEventApplyResult:
    """Apply and atomically persist one shop-floor WorkEvent."""

    if received_at.tzinfo is None or received_at.utcoffset() is None:
        raise ValueError("received_at must be timezone-aware")

    operation, attempt, snapshot = _load_execution_snapshot(
        session,
        unit_operation_id,
    )

    existing = session.get(WorkEventRow, event.event_id)
    if existing is not None:
        if existing.attempt_id != attempt.attempt_id:
            raise ValueError("event_id already belongs to a different WorkAttempt")
        return WorkEventApplyResult(snapshot=snapshot, duplicate=True)

    applied = apply_work_event(snapshot=snapshot, event=event)

    session.add(
        WorkEventRow(
            event_id=event.event_id,
            attempt_id=attempt.attempt_id,
            event_type=event.event_type.value,
            occurred_at=event.occurred_at,
            station_code=station_code,
            worker_code=worker_code,
            reason=event.reason,
            received_at=received_at,
        )
    )

    operation.state = applied.snapshot.state.value
    attempt.active_minutes = applied.snapshot.active_minutes

    if event.event_type is WorkEventType.START and attempt.started_at is None:
        attempt.started_at = event.occurred_at

    if (
        event.event_type
        in {
            WorkEventType.COMPLETE,
            WorkEventType.PASS,
            WorkEventType.FAIL,
        }
        and attempt.ended_at is None
    ):
        attempt.ended_at = event.occurred_at

    if applied.snapshot.result is not None:
        attempt.result = applied.snapshot.result.value

    session.commit()
    return applied
