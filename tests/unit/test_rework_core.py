from datetime import datetime
from zoneinfo import ZoneInfo

import pytest

from production_control.core.calendar_engine import WorkCalendar
from production_control.core.event_scheduler import schedule_operations_event_driven
from production_control.core.finite_scheduler import OperationSpec
from production_control.core.priority_rules import LotPriorityInput, PriorityRule
from production_control.core.resource_engine import Resource
from production_control.core.rework_core import (
    ReworkRole,
    ReworkTrace,
    build_final_test_rework_loop,
)
from production_control.core.slot_engine import ResourceRequirement

SEOUL = ZoneInfo("Asia/Seoul")


def dt(hour: int, minute: int = 0) -> datetime:
    return datetime(2026, 10, 5, hour, minute, tzinfo=SEOUL)


def failed_final_test() -> OperationSpec:
    return OperationSpec(
        operation_id="U03-FINAL-1",
        lot_id="LOT-A",
        unit_id="U03",
        step_seq=6,
        process_code="FINAL_TEST",
        duration_minutes=30,
        requirements=(
            ResourceRequirement("WORKER_POOL"),
            ResourceRequirement("TEST_STATION"),
        ),
        release_at=dt(9),
    )


def build_loop():
    return build_final_test_rework_loop(
        failed_final_test=failed_final_test(),
        trigger_event_id="EV-FAIL-001",
        trigger_event_type="FAIL",
        reason="temperature margin shortage",
        triggered_at=dt(11),
        tuning_operation_id="U03-TUNING-R1",
        retest_operation_id="U03-FINAL-R1",
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


def test_rework_keeps_original_routing_step_identity() -> None:
    loop = build_loop()

    assert loop.tuning.schedule_input.operation.step_seq == 4
    assert loop.final_test.schedule_input.operation.step_seq == 6
    assert loop.tuning.schedule_input.operation.process_code == "TUNING"
    assert loop.final_test.schedule_input.operation.process_code == "FINAL_TEST"


def test_rework_uses_separate_execution_order_after_failed_final_test() -> None:
    loop = build_loop()

    assert loop.tuning.schedule_input.operation.execution_seq == 7
    assert loop.final_test.schedule_input.operation.execution_seq == 8
    assert loop.tuning.schedule_input.operation.precedence_seq == 7
    assert loop.final_test.schedule_input.operation.precedence_seq == 8


def test_attempt_number_is_separate_from_rework_trigger_reason() -> None:
    loop = build_loop()

    assert loop.tuning.trace.attempt_no == 2
    assert loop.tuning.trace.role is ReworkRole.TUNING_REWORK
    assert loop.tuning.trace.trigger_source_operation_id == "U03-FINAL-1"
    assert loop.tuning.trace.trigger_event_id == "EV-FAIL-001"
    assert loop.tuning.trace.trigger_event_type == "FAIL"
    assert loop.tuning.trace.reason == "temperature margin shortage"


def test_retest_has_its_own_attempt_number_and_same_trigger_trace() -> None:
    loop = build_final_test_rework_loop(
        failed_final_test=failed_final_test(),
        trigger_event_id="EV-FAIL-001",
        trigger_event_type="FAIL",
        reason="margin shortage",
        triggered_at=dt(11),
        tuning_operation_id="U03-TUNING-R1",
        retest_operation_id="U03-FINAL-R1",
        tuning_step_seq=4,
        tuning_process_code="TUNING",
        tuning_duration_minutes=25,
        tuning_requirements=(ResourceRequirement("TUNING_STATION"),),
        tuning_attempt_no=3,
        final_test_attempt_no=2,
    )

    assert loop.tuning.trace.attempt_no == 3
    assert loop.final_test.trace.attempt_no == 2
    assert loop.final_test.trace.role is ReworkRole.FINAL_TEST_RETEST
    assert loop.final_test.trace.trigger_source_operation_id == "U03-FINAL-1"


def test_event_scheduler_runs_tuning_before_retest_despite_lower_routing_step() -> None:
    loop = build_loop()

    result = schedule_operations_event_driven(
        items=loop.schedule_inputs,
        rule=PriorityRule.EDD,
        static_lot_priorities=(
            LotPriorityInput(
                lot_id="LOT-A",
                release_at=dt(11),
                deadline=dt(17),
                remaining_work_minutes=55,
                time_until_deadline_minutes=360,
            ),
        ),
        resources={
            "WORKER_POOL": Resource("WORKER_POOL", 1),
            "TUNING_STATION": Resource("TUNING_STATION", 1),
            "TEST_STATION": Resource("TEST_STATION", 1),
        },
        calendar=WorkCalendar(),
        start_time=dt(11),
    )

    by_id = {operation.operation_id: operation for operation in result.operations}
    assert by_id["U03-TUNING-R1"].start == dt(11)
    assert by_id["U03-TUNING-R1"].end == dt(11, 25)
    assert by_id["U03-FINAL-R1"].start == dt(11, 25)
    assert by_id["U03-FINAL-R1"].end == dt(11, 55)
    assert by_id["U03-TUNING-R1"].step_seq == 4
    assert by_id["U03-FINAL-R1"].step_seq == 6


def test_retest_reuses_final_test_resource_requirements() -> None:
    loop = build_loop()

    requirements = loop.final_test.schedule_input.operation.requirements
    assert {requirement.resource_code for requirement in requirements} == {
        "WORKER_POOL",
        "TEST_STATION",
    }


def test_rework_attempt_number_must_be_second_or_later() -> None:
    with pytest.raises(ValueError):
        ReworkTrace(
            attempt_no=1,
            role=ReworkRole.TUNING_REWORK,
            trigger_source_operation_id="U03-FINAL-1",
            trigger_event_id="EV-FAIL-001",
            trigger_event_type="FAIL",
            reason="margin shortage",
        )


def test_rework_requires_traceable_reason() -> None:
    with pytest.raises(ValueError):
        ReworkTrace(
            attempt_no=2,
            role=ReworkRole.TUNING_REWORK,
            trigger_source_operation_id="U03-FINAL-1",
            trigger_event_id="EV-FAIL-001",
            trigger_event_type="FAIL",
            reason="   ",
        )


def test_rework_factory_rejects_non_final_test_source() -> None:
    source = OperationSpec(
        operation_id="U03-TUNING-1",
        lot_id="LOT-A",
        unit_id="U03",
        step_seq=4,
        process_code="TUNING",
        duration_minutes=25,
        requirements=(ResourceRequirement("TUNING_STATION"),),
        release_at=dt(9),
    )

    with pytest.raises(ValueError):
        build_final_test_rework_loop(
            failed_final_test=source,
            trigger_event_id="EV-1",
            trigger_event_type="FAIL",
            reason="not a final-test return",
            triggered_at=dt(11),
            tuning_operation_id="R1",
            retest_operation_id="R2",
            tuning_step_seq=4,
            tuning_process_code="TUNING",
            tuning_duration_minutes=25,
            tuning_requirements=(ResourceRequirement("TUNING_STATION"),),
            tuning_attempt_no=2,
            final_test_attempt_no=2,
        )
