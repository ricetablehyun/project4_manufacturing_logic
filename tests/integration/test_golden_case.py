from datetime import datetime
from zoneinfo import ZoneInfo

import pytest

from production_control.core.calendar_engine import WorkCalendar
from production_control.core.dispatch_builder import OperationDispatchInput
from production_control.core.event_scheduler import (
    EventDispatchInput,
    schedule_operations_event_driven,
)
from production_control.core.execution_state import (
    OperationExecutionSnapshot,
    WorkEventInput,
    WorkEventType,
    apply_work_event,
    materialize_final_test_rework,
)
from production_control.core.finite_scheduler import OperationSpec
from production_control.core.pace_estimator import PaceBasis, estimate_lot_process_work
from production_control.core.pace_scheduler_adapter import (
    ForecastReadiness,
    UnitPaceSchedulingInput,
    build_pace_schedule_inputs,
)
from production_control.core.priority_rules import LotPriorityInput, PriorityRule
from production_control.core.resource_engine import Resource
from production_control.core.risk_engine import RiskLevel
from production_control.core.schedule_evaluator import (
    GateTarget,
    evaluate_schedule_gates,
)
from production_control.core.slot_engine import ResourceRequirement
from production_control.domain.enums import OperationState

SEOUL = ZoneInfo("Asia/Seoul")


def dt(hour: int, minute: int = 0, second: int = 0) -> datetime:
    return datetime(2026, 10, 5, hour, minute, second, tzinfo=SEOUL)


def work_event(
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


def test_golden_case_hold_actuals_feed_pace_then_final_test_fail_adds_rework() -> None:
    """F02/F03/F04 focused flow: actuals -> Pace -> rework -> Gate risk."""

    tuning_u02 = OperationExecutionSnapshot(
        operation_id="LOT-101-U02-TUNING-1",
        lot_id="LOT-101",
        unit_id="U02",
        process_code="TUNING",
        state=OperationState.WAITING,
        attempt_no=1,
    )

    tuning_u02 = apply_work_event(
        snapshot=tuning_u02,
        event=work_event("U02-T-START", WorkEventType.START, 10),
    ).snapshot
    hold_result = apply_work_event(
        snapshot=tuning_u02,
        event=work_event(
            "U02-T-HOLD",
            WorkEventType.HOLD,
            10,
            35,
            reason="TUNING_UNSTABLE",
        ),
    )

    duplicate_hold = apply_work_event(
        snapshot=hold_result.snapshot,
        event=work_event(
            "U02-T-HOLD",
            WorkEventType.HOLD,
            10,
            35,
            reason="TUNING_UNSTABLE",
        ),
    )
    assert duplicate_hold.duplicate
    assert duplicate_hold.snapshot.active_minutes == 35
    assert duplicate_hold.snapshot.attempt_no == 1

    tuning_u02 = apply_work_event(
        snapshot=duplicate_hold.snapshot,
        event=work_event("U02-T-RESUME", WorkEventType.RESUME, 11, 30),
    ).snapshot
    tuning_u02 = apply_work_event(
        snapshot=tuning_u02,
        event=work_event("U02-T-COMPLETE", WorkEventType.COMPLETE, 12),
    ).snapshot

    assert tuning_u02.state is OperationState.COMPLETED
    assert tuning_u02.active_minutes == 65
    assert tuning_u02.attempt_no == 1

    tuning_forecast = estimate_lot_process_work(
        planned_unit_count=4,
        standard_minutes_per_unit=25,
        completed_active_minutes=[20, 25, tuning_u02.active_minutes],
        pace_min_samples=3,
    )

    assert tuning_forecast.pace_basis is PaceBasis.ACTUAL_AVERAGE
    assert tuning_forecast.pace_minutes_per_unit == pytest.approx(110 / 3)
    assert tuning_forecast.remaining_normal_work_minutes == pytest.approx(110 / 3)

    u04_tuning = UnitPaceSchedulingInput(
        operation_id="LOT-101-U04-TUNING",
        lot_id="LOT-101",
        unit_id="U04",
        step_seq=4,
        process_code="TUNING",
        state=OperationState.WAITING,
        eligible_at=dt(13, 30),
        release_at=dt(13, 30),
        requirements=(
            ResourceRequirement("WORKER_POOL"),
            ResourceRequirement("TUNING_STATION"),
        ),
    )
    u04_tuning_adapter = build_pace_schedule_inputs(
        forecast=tuning_forecast,
        units=(u04_tuning,),
    )

    assert u04_tuning_adapter.readiness is ForecastReadiness.READY
    assert (
        u04_tuning_adapter.items[0].operation.duration_minutes
        == pytest.approx(110 / 3)
    )

    failed_final_test = OperationSpec(
        operation_id="LOT-101-U03-FINAL-1",
        lot_id="LOT-101",
        unit_id="U03",
        step_seq=6,
        process_code="FINAL_TEST",
        duration_minutes=30,
        requirements=(
            ResourceRequirement("WORKER_POOL"),
            ResourceRequirement("TEST_STATION"),
        ),
        release_at=dt(13),
        execution_seq=6,
    )
    final_u03 = OperationExecutionSnapshot(
        operation_id=failed_final_test.operation_id,
        lot_id="LOT-101",
        unit_id="U03",
        process_code="FINAL_TEST",
        state=OperationState.WAITING,
        attempt_no=1,
    )
    final_u03 = apply_work_event(
        snapshot=final_u03,
        event=work_event("U03-F-START", WorkEventType.START, 13),
    ).snapshot
    fail_result = apply_work_event(
        snapshot=final_u03,
        event=work_event(
            "U03-F-FAIL",
            WorkEventType.FAIL,
            13,
            30,
            reason="temperature margin shortage",
        ),
    )

    rework = materialize_final_test_rework(
        event_result=fail_result,
        failed_final_test=failed_final_test,
        tuning_operation_id="LOT-101-U03-TUNING-R1",
        retest_operation_id="LOT-101-U03-FINAL-R1",
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

    assert rework.tuning.trace.attempt_no == 2
    assert rework.tuning.trace.trigger_event_id == "U03-F-FAIL"
    assert rework.tuning.trace.reason == "temperature margin shortage"

    u04_final_operation = OperationSpec(
        operation_id="LOT-101-U04-FINAL",
        lot_id="LOT-101",
        unit_id="U04",
        step_seq=6,
        process_code="FINAL_TEST",
        duration_minutes=30,
        requirements=(
            ResourceRequirement("WORKER_POOL"),
            ResourceRequirement("TEST_STATION"),
        ),
        release_at=dt(13, 30),
        execution_seq=6,
    )
    u04_final = EventDispatchInput(
        operation=u04_final_operation,
        dispatch=OperationDispatchInput(
            operation_id=u04_final_operation.operation_id,
            lot_id="LOT-101",
            unit_id="U04",
            state=OperationState.WAITING,
            eligible_at=dt(13, 30),
        ),
    )

    schedule = schedule_operations_event_driven(
        items=(
            *rework.schedule_inputs,
            *u04_tuning_adapter.items,
            u04_final,
        ),
        rule=PriorityRule.EDD,
        static_lot_priorities=(
            LotPriorityInput(
                lot_id="LOT-101",
                release_at=dt(9),
                deadline=dt(15, 30),
                remaining_work_minutes=25 + 30 + 110 / 3 + 30,
                time_until_deadline_minutes=120,
            ),
        ),
        resources={
            "WORKER_POOL": Resource("WORKER_POOL", 2),
            "TUNING_STATION": Resource("TUNING_STATION", 1),
            "TEST_STATION": Resource("TEST_STATION", 1),
        },
        calendar=WorkCalendar(),
        start_time=dt(13, 30),
    )

    by_id = {operation.operation_id: operation for operation in schedule.operations}

    assert by_id["LOT-101-U03-TUNING-R1"].start == dt(13, 30)
    assert by_id["LOT-101-U03-TUNING-R1"].end == dt(13, 55)
    assert by_id["LOT-101-U03-FINAL-R1"].start == dt(13, 55)
    assert by_id["LOT-101-U03-FINAL-R1"].end == dt(14, 25)
    assert by_id["LOT-101-U04-TUNING"].start == dt(13, 55)
    assert by_id["LOT-101-U04-TUNING"].end == dt(14, 31, 40)
    assert by_id["LOT-101-U04-FINAL"].start == dt(14, 31, 40)
    assert by_id["LOT-101-U04-FINAL"].end == dt(15, 1, 40)

    gate = evaluate_schedule_gates(
        scheduled_operations=schedule.operations,
        gate_targets=(
            GateTarget(
                gate_id="LOT-101-SHIPPING-INSPECTION",
                lot_id="LOT-101",
                required_step_seq=6,
                planned_at=dt(15, 30),
            ),
        ),
        warning_threshold_minutes=120,
    )[0]

    assert gate.forecast_at == dt(15, 1, 40)
    assert gate.risk.risk_level is RiskLevel.WARNING
    assert gate.risk.slack_minutes == pytest.approx(28 + 20 / 60)
