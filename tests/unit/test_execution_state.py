from datetime import datetime
from zoneinfo import ZoneInfo

import pytest

from production_control.core.execution_state import (
    AttemptResult,
    OperationExecutionSnapshot,
    WorkEventInput,
    WorkEventType,
    apply_work_event,
    materialize_final_test_rework,
)
from production_control.core.finite_scheduler import OperationSpec
from production_control.core.rework_core import ReworkRole
from production_control.core.slot_engine import ResourceRequirement
from production_control.domain.enums import OperationState

SEOUL = ZoneInfo("Asia/Seoul")


def dt(hour: int, minute: int = 0) -> datetime:
    return datetime(2026, 10, 5, hour, minute, tzinfo=SEOUL)


def snapshot(
    *,
    process_code: str = "TUNING",
    attempt_no: int = 1,
) -> OperationExecutionSnapshot:
    return OperationExecutionSnapshot(
        operation_id="OP-1",
        lot_id="LOT-101",
        unit_id="U02",
        process_code=process_code,
        state=OperationState.WAITING,
        attempt_no=attempt_no,
    )


def event(
    event_id: str,
    event_type: WorkEventType,
    hour: int,
    minute: int = 0,
    *,
    reason: str | None = None,
) -> WorkEventInput:
    return WorkEventInput(
        event_id=event_id,
        event_type=event_type,
        occurred_at=dt(hour, minute),
        reason=reason,
    )


def test_start_moves_waiting_attempt_to_running() -> None:
    result = apply_work_event(
        snapshot=snapshot(),
        event=event("E1", WorkEventType.START, 10),
    )

    assert result.snapshot.state is OperationState.RUNNING
    assert result.snapshot.active_started_at == dt(10)
    assert result.snapshot.attempt_no == 1


def test_hold_releases_active_segment_but_keeps_attempt_number() -> None:
    started = apply_work_event(
        snapshot=snapshot(),
        event=event("E1", WorkEventType.START, 10),
    ).snapshot

    held = apply_work_event(
        snapshot=started,
        event=event(
            "E2",
            WorkEventType.HOLD,
            10,
            35,
            reason="TUNING_UNSTABLE",
        ),
    ).snapshot

    assert held.state is OperationState.HOLD
    assert held.active_minutes == 35
    assert held.active_started_at is None
    assert held.attempt_no == 1
    assert held.last_hold_reason == "TUNING_UNSTABLE"


def test_hold_resume_complete_excludes_hold_waiting_time() -> None:
    state = apply_work_event(
        snapshot=snapshot(),
        event=event("E1", WorkEventType.START, 10),
    ).snapshot
    state = apply_work_event(
        snapshot=state,
        event=event("E2", WorkEventType.HOLD, 10, 35, reason="TUNING_UNSTABLE"),
    ).snapshot
    state = apply_work_event(
        snapshot=state,
        event=event("E3", WorkEventType.RESUME, 11, 30),
    ).snapshot
    state = apply_work_event(
        snapshot=state,
        event=event("E4", WorkEventType.COMPLETE, 12),
    ).snapshot

    assert state.state is OperationState.COMPLETED
    assert state.active_minutes == 65
    assert state.attempt_no == 1


def test_duplicate_event_id_is_idempotent() -> None:
    started_result = apply_work_event(
        snapshot=snapshot(),
        event=event("E1", WorkEventType.START, 10),
    )

    duplicate = apply_work_event(
        snapshot=started_result.snapshot,
        event=event("E1", WorkEventType.START, 10),
    )

    assert duplicate.duplicate
    assert duplicate.snapshot == started_result.snapshot
    assert duplicate.snapshot.seen_event_ids == ("E1",)


def test_hold_requires_worker_reason() -> None:
    started = apply_work_event(
        snapshot=snapshot(),
        event=event("E1", WorkEventType.START, 10),
    ).snapshot

    with pytest.raises(ValueError):
        apply_work_event(
            snapshot=started,
            event=event("E2", WorkEventType.HOLD, 10, 30),
        )


def test_final_test_fail_completes_attempt_and_emits_rework_trigger() -> None:
    state = apply_work_event(
        snapshot=snapshot(process_code="FINAL_TEST"),
        event=event("E1", WorkEventType.START, 10),
    ).snapshot

    result = apply_work_event(
        snapshot=state,
        event=event(
            "E2",
            WorkEventType.FAIL,
            10,
            30,
            reason="temperature margin shortage",
        ),
    )

    assert result.snapshot.state is OperationState.COMPLETED
    assert result.snapshot.result is AttemptResult.FAIL
    assert result.snapshot.active_minutes == 30
    assert result.rework_trigger is not None
    assert result.rework_trigger.source_operation_id == "OP-1"
    assert result.rework_trigger.source_attempt_no == 1
    assert result.rework_trigger.reason == "temperature margin shortage"


def test_final_test_fail_requires_traceable_reason() -> None:
    state = apply_work_event(
        snapshot=snapshot(process_code="FINAL_TEST"),
        event=event("E1", WorkEventType.START, 10),
    ).snapshot

    with pytest.raises(ValueError):
        apply_work_event(
            snapshot=state,
            event=event("E2", WorkEventType.FAIL, 10, 30),
        )


def test_pass_completes_without_rework_trigger() -> None:
    state = apply_work_event(
        snapshot=snapshot(process_code="FINAL_TEST"),
        event=event("E1", WorkEventType.START, 10),
    ).snapshot

    result = apply_work_event(
        snapshot=state,
        event=event("E2", WorkEventType.PASS, 10, 30),
    )

    assert result.snapshot.result is AttemptResult.PASS
    assert result.rework_trigger is None


def test_complete_then_pass_can_attach_result_without_more_active_time() -> None:
    state = apply_work_event(
        snapshot=snapshot(process_code="FINAL_TEST"),
        event=event("E1", WorkEventType.START, 10),
    ).snapshot
    state = apply_work_event(
        snapshot=state,
        event=event("E2", WorkEventType.COMPLETE, 10, 30),
    ).snapshot

    result = apply_work_event(
        snapshot=state,
        event=event("E3", WorkEventType.PASS, 10, 31),
    )

    assert result.snapshot.active_minutes == 30
    assert result.snapshot.result is AttemptResult.PASS


def test_invalid_resume_without_hold_is_rejected() -> None:
    with pytest.raises(ValueError):
        apply_work_event(
            snapshot=snapshot(),
            event=event("E1", WorkEventType.RESUME, 10),
        )


def test_final_test_fail_materializes_traceable_tuning_and_retest() -> None:
    state = apply_work_event(
        snapshot=snapshot(process_code="FINAL_TEST"),
        event=event("E1", WorkEventType.START, 10),
    ).snapshot
    fail_result = apply_work_event(
        snapshot=state,
        event=event(
            "E2",
            WorkEventType.FAIL,
            10,
            30,
            reason="margin shortage",
        ),
    )

    failed_operation = OperationSpec(
        operation_id="OP-1",
        lot_id="LOT-101",
        unit_id="U02",
        step_seq=6,
        process_code="FINAL_TEST",
        duration_minutes=30,
        requirements=(
            ResourceRequirement("WORKER_POOL"),
            ResourceRequirement("TEST_STATION"),
        ),
        release_at=dt(10),
    )

    loop = materialize_final_test_rework(
        event_result=fail_result,
        failed_final_test=failed_operation,
        tuning_operation_id="OP-2",
        retest_operation_id="OP-3",
        tuning_step_seq=4,
        tuning_process_code="TUNING",
        tuning_duration_minutes=25,
        tuning_requirements=(
            ResourceRequirement("WORKER_POOL"),
            ResourceRequirement("TUNING_STATION"),
        ),
        tuning_attempt_no=2,
        final_test_attempt_no=2,
    )

    assert loop.tuning.trace.role is ReworkRole.TUNING_REWORK
    assert loop.tuning.trace.trigger_event_id == "E2"
    assert loop.tuning.trace.reason == "margin shortage"
    assert loop.tuning.schedule_input.operation.release_at == dt(10, 30)
    assert loop.final_test.trace.role is ReworkRole.FINAL_TEST_RETEST


def test_nonduplicate_older_event_is_rejected() -> None:
    started = apply_work_event(
        snapshot=snapshot(),
        event=event("E1", WorkEventType.START, 10),
    ).snapshot

    with pytest.raises(ValueError):
        apply_work_event(
            snapshot=started,
            event=event("E2", WorkEventType.HOLD, 9, 59, reason="late packet"),
        )
