"""Confirmed FINAL_TEST -> TUNING -> FINAL_TEST rework scheduling.

Attempt number answers "which execution attempt is this?" while trigger
metadata answers "why did this attempt exist?". HOLD/RESUME remains inside one
attempt and is therefore outside this module.
"""

from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum

from production_control.core.dispatch_builder import OperationDispatchInput
from production_control.core.event_scheduler import EventDispatchInput
from production_control.core.finite_scheduler import OperationSpec
from production_control.core.slot_engine import ResourceRequirement
from production_control.domain.enums import OperationState


class ReworkRole(StrEnum):
    TUNING_REWORK = "TUNING_REWORK"
    FINAL_TEST_RETEST = "FINAL_TEST_RETEST"


@dataclass(frozen=True, slots=True)
class ReworkTrace:
    """Traceability attached to one newly created rework/retest operation."""

    attempt_no: int
    role: ReworkRole
    trigger_source_operation_id: str
    trigger_event_id: str
    trigger_event_type: str
    reason: str

    def __post_init__(self) -> None:
        if self.attempt_no < 2:
            raise ValueError("rework attempt_no must be 2 or greater")
        if not self.trigger_source_operation_id:
            raise ValueError("trigger_source_operation_id must not be empty")
        if not self.trigger_event_id:
            raise ValueError("trigger_event_id must not be empty")
        if not self.trigger_event_type:
            raise ValueError("trigger_event_type must not be empty")
        if not self.reason.strip():
            raise ValueError("reason must not be empty")


@dataclass(frozen=True, slots=True)
class ConfirmedReworkItem:
    """Scheduler input plus the reason that the repeated operation exists."""

    schedule_input: EventDispatchInput
    trace: ReworkTrace


@dataclass(frozen=True, slots=True)
class ConfirmedReworkLoop:
    tuning: ConfirmedReworkItem
    final_test: ConfirmedReworkItem

    @property
    def schedule_inputs(self) -> tuple[EventDispatchInput, EventDispatchInput]:
        return (self.tuning.schedule_input, self.final_test.schedule_input)


def _waiting_dispatch(operation: OperationSpec, *, eligible_at: datetime) -> EventDispatchInput:
    return EventDispatchInput(
        operation=operation,
        dispatch=OperationDispatchInput(
            operation_id=operation.operation_id,
            lot_id=operation.lot_id,
            unit_id=operation.unit_id,
            state=OperationState.WAITING,
            eligible_at=eligible_at,
        ),
    )


def build_final_test_rework_loop(
    *,
    failed_final_test: OperationSpec,
    trigger_event_id: str,
    trigger_event_type: str,
    reason: str,
    triggered_at: datetime,
    tuning_operation_id: str,
    retest_operation_id: str,
    tuning_step_seq: int,
    tuning_process_code: str,
    tuning_duration_minutes: float,
    tuning_requirements: tuple[ResourceRequirement, ...],
    tuning_attempt_no: int,
    final_test_attempt_no: int,
) -> ConfirmedReworkLoop:
    """Create explicit re-tuning and re-test work after a FINAL_TEST return."""

    if failed_final_test.process_code != "FINAL_TEST":
        raise ValueError("failed_final_test must be a FINAL_TEST operation")
    if tuning_operation_id == retest_operation_id:
        raise ValueError("rework operation_id values must be different")
    if tuning_operation_id == failed_final_test.operation_id:
        raise ValueError("tuning_operation_id must differ from failed FINAL_TEST")
    if retest_operation_id == failed_final_test.operation_id:
        raise ValueError("retest_operation_id must differ from failed FINAL_TEST")
    if not tuning_process_code:
        raise ValueError("tuning_process_code must not be empty")

    source_execution_seq = failed_final_test.precedence_seq

    tuning_operation = OperationSpec(
        operation_id=tuning_operation_id,
        lot_id=failed_final_test.lot_id,
        unit_id=failed_final_test.unit_id,
        step_seq=tuning_step_seq,
        process_code=tuning_process_code,
        duration_minutes=tuning_duration_minutes,
        requirements=tuning_requirements,
        release_at=triggered_at,
        execution_seq=source_execution_seq + 1,
    )
    retest_operation = OperationSpec(
        operation_id=retest_operation_id,
        lot_id=failed_final_test.lot_id,
        unit_id=failed_final_test.unit_id,
        step_seq=failed_final_test.step_seq,
        process_code=failed_final_test.process_code,
        duration_minutes=failed_final_test.duration_minutes,
        requirements=failed_final_test.requirements,
        release_at=triggered_at,
        execution_seq=source_execution_seq + 2,
    )

    common_trace = dict(
        trigger_source_operation_id=failed_final_test.operation_id,
        trigger_event_id=trigger_event_id,
        trigger_event_type=trigger_event_type,
        reason=reason,
    )

    return ConfirmedReworkLoop(
        tuning=ConfirmedReworkItem(
            schedule_input=_waiting_dispatch(
                tuning_operation,
                eligible_at=triggered_at,
            ),
            trace=ReworkTrace(
                attempt_no=tuning_attempt_no,
                role=ReworkRole.TUNING_REWORK,
                **common_trace,
            ),
        ),
        final_test=ConfirmedReworkItem(
            schedule_input=_waiting_dispatch(
                retest_operation,
                eligible_at=triggered_at,
            ),
            trace=ReworkTrace(
                attempt_no=final_test_attempt_no,
                role=ReworkRole.FINAL_TEST_RETEST,
                **common_trace,
            ),
        ),
    )
