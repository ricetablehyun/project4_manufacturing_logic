"""Transactional WorkEvent persistence backed by the pure execution-state core."""

from datetime import datetime

from sqlalchemy import func, select
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
        select(WorkEventRow).where(WorkEventRow.attempt_id == attempt.attempt_id)
    ).all()
    events.sort(key=lambda row: (row.occurred_at, row.event_id))

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


def _load_unit_operation_for_process(
    session: Session,
    *,
    unit_id: str,
    process_code: str,
) -> UnitOperationRow:
    operations = session.scalars(
        select(UnitOperationRow)
        .join(
            RoutingStepRow,
            UnitOperationRow.routing_step_id == RoutingStepRow.routing_step_id,
        )
        .join(ProcessRow, RoutingStepRow.process_id == ProcessRow.process_id)
        .where(
            UnitOperationRow.unit_id == unit_id,
            ProcessRow.process_code == process_code,
        )
    ).all()
    if len(operations) != 1:
        raise ValueError(
            "expected exactly one UnitOperation for "
            f"unit={unit_id}, process={process_code}; found {len(operations)}"
        )
    return operations[0]


def _create_next_rework_attempt(
    session: Session,
    *,
    operation: UnitOperationRow,
    role: str,
    source_operation_id: str,
    source_event_id: str,
    detail: str,
    eligible_at: datetime,
) -> WorkAttemptRow:
    if operation.state != OperationState.COMPLETED.value:
        raise ValueError(
            "rework target UnitOperation must be COMPLETED before a new Attempt"
        )

    max_attempt_no = session.scalar(
        select(func.max(WorkAttemptRow.attempt_no)).where(
            WorkAttemptRow.unit_operation_id == operation.unit_operation_id
        )
    )
    next_attempt_no = int(max_attempt_no or 0) + 1
    attempt = WorkAttemptRow(
        attempt_id=(
            f"ATTEMPT::{operation.unit_operation_id}::{next_attempt_no}"
        ),
        unit_operation_id=operation.unit_operation_id,
        attempt_no=next_attempt_no,
        active_minutes=0,
        rework_role=role,
        rework_source_ref=source_operation_id,
        rework_event_ref=source_event_id,
        rework_detail=detail,
    )
    session.add(attempt)
    operation.current_attempt_no = next_attempt_no
    operation.state = OperationState.WAITING.value
    operation.eligible_at = eligible_at
    return attempt


def _stage_rework_after_event(
    *,
    session: Session,
    operation: UnitOperationRow,
    attempt: WorkAttemptRow,
    applied: WorkEventApplyResult,
    event: WorkEventInput,
) -> None:
    trigger = applied.rework_trigger
    if trigger is not None:
        tuning = _load_unit_operation_for_process(
            session,
            unit_id=applied.snapshot.unit_id,
            process_code="TUNING",
        )
        _create_next_rework_attempt(
            session,
            operation=tuning,
            role="TUNING_REWORK",
            source_operation_id=trigger.source_operation_id,
            source_event_id=trigger.event_id,
            detail=trigger.reason,
            eligible_at=trigger.occurred_at,
        )
        return

    if (
        event.event_type is WorkEventType.COMPLETE
        and applied.snapshot.process_code == "TUNING"
        and attempt.rework_role == "TUNING_REWORK"
    ):
        if not attempt.rework_source_ref:
            raise ValueError("TUNING_REWORK Attempt is missing its source operation")
        if not attempt.rework_event_ref:
            raise ValueError("TUNING_REWORK Attempt is missing its source event")
        if not attempt.rework_detail:
            raise ValueError("TUNING_REWORK Attempt is missing its rework detail")

        final_test = _load_unit_operation_for_process(
            session,
            unit_id=applied.snapshot.unit_id,
            process_code="FINAL_TEST",
        )
        _create_next_rework_attempt(
            session,
            operation=final_test,
            role="FINAL_TEST_RETEST",
            source_operation_id=attempt.rework_source_ref,
            source_event_id=attempt.rework_event_ref,
            detail=attempt.rework_detail,
            eligible_at=event.occurred_at,
        )


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

    session.flush()
    _stage_rework_after_event(
        session=session,
        operation=operation,
        attempt=attempt,
        applied=applied,
        event=event,
    )
    session.commit()
    return applied
