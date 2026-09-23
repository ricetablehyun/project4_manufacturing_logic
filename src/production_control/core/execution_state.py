"""Pure WorkEvent -> execution-state transitions for one UnitOperation attempt.

This module keeps execution facts separate from planning:
- START / HOLD / RESUME / COMPLETE / PASS / FAIL update one attempt snapshot.
- HOLD / RESUME never increments attempt_no.
- active_minutes excludes HOLD waiting time.
- event_id is idempotent within the supplied snapshot.
- FINAL_TEST FAIL emits a traceable rework trigger; it does not silently invent
  a cause or mutate Routing master data.
"""

from dataclasses import dataclass, replace
from datetime import datetime
from enum import StrEnum

from production_control.core.finite_scheduler import OperationSpec
from production_control.core.rework_core import (
    ConfirmedReworkLoop,
    build_final_test_rework_loop,
)
from production_control.core.slot_engine import ResourceRequirement
from production_control.domain.enums import OperationState


class WorkEventType(StrEnum):
    START = "START"
    HOLD = "HOLD"
    RESUME = "RESUME"
    COMPLETE = "COMPLETE"
    PASS = "PASS"
    FAIL = "FAIL"


class AttemptResult(StrEnum):
    PASS = "PASS"
    FAIL = "FAIL"


@dataclass(frozen=True, slots=True)
class WorkEventInput:
    event_id: str
    event_type: WorkEventType
    occurred_at: datetime
    reason: str | None = None

    def __post_init__(self) -> None:
        if not self.event_id:
            raise ValueError("event_id must not be empty")
        if self.occurred_at.tzinfo is None or self.occurred_at.utcoffset() is None:
            raise ValueError("occurred_at must be timezone-aware")


@dataclass(frozen=True, slots=True)
class OperationExecutionSnapshot:
    """Current execution view for exactly one WorkAttempt."""

    operation_id: str
    lot_id: str
    unit_id: str
    process_code: str
    state: OperationState
    attempt_no: int = 1
    active_minutes: float = 0.0
    active_started_at: datetime | None = None
    last_event_at: datetime | None = None
    result: AttemptResult | None = None
    last_hold_reason: str | None = None
    seen_event_ids: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if not self.operation_id:
            raise ValueError("operation_id must not be empty")
        if not self.lot_id:
            raise ValueError("lot_id must not be empty")
        if not self.unit_id:
            raise ValueError("unit_id must not be empty")
        if not self.process_code:
            raise ValueError("process_code must not be empty")
        if self.attempt_no <= 0:
            raise ValueError("attempt_no must be greater than 0")
        if self.active_minutes < 0:
            raise ValueError("active_minutes must be 0 or greater")
        if self.state is OperationState.RUNNING and self.active_started_at is None:
            raise ValueError("RUNNING snapshot requires active_started_at")
        if self.state is not OperationState.RUNNING and self.active_started_at is not None:
            raise ValueError("only RUNNING snapshot may have active_started_at")


@dataclass(frozen=True, slots=True)
class FinalTestReworkTrigger:
    source_operation_id: str
    source_attempt_no: int
    event_id: str
    event_type: WorkEventType
    occurred_at: datetime
    reason: str


@dataclass(frozen=True, slots=True)
class WorkEventApplyResult:
    snapshot: OperationExecutionSnapshot
    duplicate: bool
    rework_trigger: FinalTestReworkTrigger | None = None


def _require_reason(event: WorkEventInput, *, label: str) -> str:
    reason = (event.reason or "").strip()
    if not reason:
        raise ValueError(f"{label} requires a non-empty reason")
    return reason


def _append_event_id(
    snapshot: OperationExecutionSnapshot,
    event: WorkEventInput,
    **changes: object,
) -> OperationExecutionSnapshot:
    return replace(
        snapshot,
        seen_event_ids=(*snapshot.seen_event_ids, event.event_id),
        last_event_at=event.occurred_at,
        **changes,
    )


def _active_minutes_until(
    snapshot: OperationExecutionSnapshot,
    occurred_at: datetime,
) -> float:
    if snapshot.active_started_at is None:
        raise ValueError("RUNNING snapshot is missing active_started_at")
    if occurred_at < snapshot.active_started_at:
        raise ValueError("event cannot occur before the current active segment started")
    return snapshot.active_minutes + (
        occurred_at - snapshot.active_started_at
    ).total_seconds() / 60.0


def _validate_event_order(
    snapshot: OperationExecutionSnapshot,
    event: WorkEventInput,
) -> None:
    if snapshot.last_event_at is not None and event.occurred_at < snapshot.last_event_at:
        raise ValueError("non-duplicate events must not move execution time backward")


def apply_work_event(
    *,
    snapshot: OperationExecutionSnapshot,
    event: WorkEventInput,
) -> WorkEventApplyResult:
    """Apply one idempotent WorkEvent to one attempt snapshot."""

    if event.event_id in snapshot.seen_event_ids:
        return WorkEventApplyResult(snapshot=snapshot, duplicate=True)

    _validate_event_order(snapshot, event)

    if event.event_type is WorkEventType.START:
        if snapshot.state is not OperationState.WAITING:
            raise ValueError("START requires WAITING state")
        updated = _append_event_id(
            snapshot,
            event,
            state=OperationState.RUNNING,
            active_started_at=event.occurred_at,
        )
        return WorkEventApplyResult(snapshot=updated, duplicate=False)

    if event.event_type is WorkEventType.HOLD:
        if snapshot.state is not OperationState.RUNNING:
            raise ValueError("HOLD requires RUNNING state")
        reason = _require_reason(event, label="HOLD")
        updated = _append_event_id(
            snapshot,
            event,
            state=OperationState.HOLD,
            active_minutes=_active_minutes_until(snapshot, event.occurred_at),
            active_started_at=None,
            last_hold_reason=reason,
        )
        return WorkEventApplyResult(snapshot=updated, duplicate=False)

    if event.event_type is WorkEventType.RESUME:
        if snapshot.state is not OperationState.HOLD:
            raise ValueError("RESUME requires HOLD state")
        updated = _append_event_id(
            snapshot,
            event,
            state=OperationState.RUNNING,
            active_started_at=event.occurred_at,
        )
        return WorkEventApplyResult(snapshot=updated, duplicate=False)

    if event.event_type is WorkEventType.COMPLETE:
        if snapshot.state is not OperationState.RUNNING:
            raise ValueError("COMPLETE requires RUNNING state")
        updated = _append_event_id(
            snapshot,
            event,
            state=OperationState.COMPLETED,
            active_minutes=_active_minutes_until(snapshot, event.occurred_at),
            active_started_at=None,
        )
        return WorkEventApplyResult(snapshot=updated, duplicate=False)

    if event.event_type in (WorkEventType.PASS, WorkEventType.FAIL):
        if snapshot.state not in (OperationState.RUNNING, OperationState.COMPLETED):
            raise ValueError("PASS/FAIL requires RUNNING or COMPLETED state")
        if snapshot.result is not None:
            raise ValueError("attempt result is already set")

        active_minutes = snapshot.active_minutes
        if snapshot.state is OperationState.RUNNING:
            active_minutes = _active_minutes_until(snapshot, event.occurred_at)

        result = (
            AttemptResult.PASS
            if event.event_type is WorkEventType.PASS
            else AttemptResult.FAIL
        )
        updated = _append_event_id(
            snapshot,
            event,
            state=OperationState.COMPLETED,
            active_minutes=active_minutes,
            active_started_at=None,
            result=result,
        )

        trigger = None
        if (
            event.event_type is WorkEventType.FAIL
            and snapshot.process_code == "FINAL_TEST"
        ):
            reason = _require_reason(event, label="FINAL_TEST FAIL")
            trigger = FinalTestReworkTrigger(
                source_operation_id=snapshot.operation_id,
                source_attempt_no=snapshot.attempt_no,
                event_id=event.event_id,
                event_type=event.event_type,
                occurred_at=event.occurred_at,
                reason=reason,
            )

        return WorkEventApplyResult(
            snapshot=updated,
            duplicate=False,
            rework_trigger=trigger,
        )

    raise ValueError(f"unsupported WorkEvent type: {event.event_type}")


def materialize_final_test_rework(
    *,
    event_result: WorkEventApplyResult,
    failed_final_test: OperationSpec,
    tuning_operation_id: str,
    retest_operation_id: str,
    tuning_step_seq: int,
    tuning_process_code: str,
    tuning_duration_minutes: float,
    tuning_requirements: tuple[ResourceRequirement, ...],
    tuning_attempt_no: int,
    final_test_attempt_no: int,
) -> ConfirmedReworkLoop:
    """Turn an accepted FINAL_TEST FAIL trigger into scheduler rework inputs."""

    trigger = event_result.rework_trigger
    if trigger is None:
        raise ValueError("event result does not contain a FINAL_TEST rework trigger")
    if trigger.source_operation_id != failed_final_test.operation_id:
        raise ValueError("rework trigger source does not match failed FINAL_TEST operation")

    return build_final_test_rework_loop(
        failed_final_test=failed_final_test,
        trigger_event_id=trigger.event_id,
        trigger_event_type=trigger.event_type.value,
        reason=trigger.reason,
        triggered_at=trigger.occurred_at,
        tuning_operation_id=tuning_operation_id,
        retest_operation_id=retest_operation_id,
        tuning_step_seq=tuning_step_seq,
        tuning_process_code=tuning_process_code,
        tuning_duration_minutes=tuning_duration_minutes,
        tuning_requirements=tuning_requirements,
        tuning_attempt_no=tuning_attempt_no,
        final_test_attempt_no=final_test_attempt_no,
    )
