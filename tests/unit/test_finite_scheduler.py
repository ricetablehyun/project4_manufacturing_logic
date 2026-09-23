from datetime import datetime
from zoneinfo import ZoneInfo

import pytest

from production_control.core.calendar_engine import WorkCalendar
from production_control.core.finite_scheduler import (
    OperationSpec,
    aggregate_lot_process_forecast,
    schedule_operations,
)
from production_control.core.resource_engine import Resource
from production_control.core.slot_engine import ResourceRequirement

SEOUL = ZoneInfo("Asia/Seoul")


def dt(hour: int, minute: int = 0) -> datetime:
    return datetime(2026, 10, 5, hour, minute, tzinfo=SEOUL)


def worker() -> tuple[ResourceRequirement, ...]:
    return (ResourceRequirement("WORKER_POOL", 1),)


def tuning() -> tuple[ResourceRequirement, ...]:
    return (
        ResourceRequirement("WORKER_POOL", 1),
        ResourceRequirement("TUNING_STATION", 1),
    )


def resources() -> dict[str, Resource]:
    return {
        "WORKER_POOL": Resource("WORKER_POOL", capacity=2),
        "TUNING_STATION": Resource("TUNING_STATION", capacity=1),
    }


def op(
    operation_id: str,
    unit_id: str,
    step_seq: int,
    process_code: str,
    duration: float,
    requirements: tuple[ResourceRequirement, ...],
    *,
    buffer_k: int | None = None,
    execution_seq: int | None = None,
) -> OperationSpec:
    return OperationSpec(
        operation_id=operation_id,
        lot_id="LOT-01",
        unit_id=unit_id,
        step_seq=step_seq,
        process_code=process_code,
        duration_minutes=duration,
        requirements=requirements,
        release_at=dt(9),
        release_buffer_k=buffer_k,
        execution_seq=execution_seq,
    )


def test_worker_pool_capacity_two_schedules_two_units_in_parallel() -> None:
    operations = (
        op("U1-A", "U1", 1, "ASSEMBLY", 10, worker()),
        op("U2-A", "U2", 1, "ASSEMBLY", 10, worker()),
    )

    result = schedule_operations(
        operations=operations,
        dispatch_sequence=("U1-A", "U2-A"),
        resources=resources(),
        calendar=WorkCalendar(),
    )

    assert result.operations[0].start == dt(9)
    assert result.operations[1].start == dt(9)
    assert result.operations[0].end == dt(9, 10)
    assert result.operations[1].end == dt(9, 10)


def test_single_tuning_station_serializes_units() -> None:
    operations = (
        op("U1-T", "U1", 1, "TUNING", 25, tuning()),
        op("U2-T", "U2", 1, "TUNING", 25, tuning()),
    )

    result = schedule_operations(
        operations=operations,
        dispatch_sequence=("U1-T", "U2-T"),
        resources=resources(),
        calendar=WorkCalendar(),
    )

    assert result.operations[0].start == dt(9)
    assert result.operations[0].end == dt(9, 25)
    assert result.operations[1].start == dt(9, 25)
    assert result.operations[1].end == dt(9, 50)


def test_routing_precedence_sets_next_step_earliest_start() -> None:
    operations = (
        op("U1-A", "U1", 1, "ASSEMBLY", 10, worker()),
        op("U1-T", "U1", 2, "TUNING", 25, tuning()),
    )

    result = schedule_operations(
        operations=operations,
        dispatch_sequence=("U1-T", "U1-A"),
        resources=resources(),
        calendar=WorkCalendar(),
    )

    by_id = {operation.operation_id: operation for operation in result.operations}
    assert by_id["U1-A"].start == dt(9)
    assert by_id["U1-A"].end == dt(9, 10)
    assert by_id["U1-T"].start == dt(9, 10)


def test_initial_buffer_k_delays_first_downstream_operation() -> None:
    operations = (
        op("U1-T", "U1", 1, "TUNING", 25, tuning()),
        op("U2-T", "U2", 1, "TUNING", 25, tuning()),
        op("U1-F", "U1", 2, "FINISH", 10, worker(), buffer_k=2),
        op("U2-F", "U2", 2, "FINISH", 10, worker(), buffer_k=2),
    )

    result = schedule_operations(
        operations=operations,
        dispatch_sequence=("U1-T", "U1-F", "U2-T", "U2-F"),
        resources=resources(),
        calendar=WorkCalendar(),
    )

    by_id = {operation.operation_id: operation for operation in result.operations}
    assert by_id["U1-T"].end == dt(9, 25)
    assert by_id["U2-T"].end == dt(9, 50)
    assert by_id["U1-F"].start == dt(9, 50)


def test_after_initial_buffer_release_flow_is_continuous() -> None:
    operations = (
        op("U1-A", "U1", 1, "ASSEMBLY", 10, worker()),
        op("U2-A", "U2", 1, "ASSEMBLY", 10, worker()),
        op("U3-A", "U3", 1, "ASSEMBLY", 10, worker()),
        op("U1-T", "U1", 2, "TUNING", 25, tuning()),
        op("U2-T", "U2", 2, "TUNING", 25, tuning()),
        op("U3-T", "U3", 2, "TUNING", 25, tuning()),
        op("U1-F", "U1", 3, "FINISH", 10, worker(), buffer_k=2),
        op("U2-F", "U2", 3, "FINISH", 10, worker(), buffer_k=2),
        op("U3-F", "U3", 3, "FINISH", 10, worker(), buffer_k=2),
    )

    result = schedule_operations(
        operations=operations,
        dispatch_sequence=(
            "U1-A",
            "U2-A",
            "U3-A",
            "U1-T",
            "U2-T",
            "U1-F",
            "U3-T",
            "U3-F",
            "U2-F",
        ),
        resources=resources(),
        calendar=WorkCalendar(),
    )

    by_id = {operation.operation_id: operation for operation in result.operations}
    assert by_id["U1-F"].start == dt(10)
    assert by_id["U3-T"].start == dt(10)
    assert by_id["U3-T"].end == dt(10, 25)
    assert by_id["U3-F"].start == dt(10, 25)


def test_dispatch_sequence_controls_ready_operation_order() -> None:
    operations = (
        op("U1-T", "U1", 1, "TUNING", 25, tuning()),
        op("U2-T", "U2", 1, "TUNING", 25, tuning()),
    )

    result = schedule_operations(
        operations=operations,
        dispatch_sequence=("U2-T", "U1-T"),
        resources=resources(),
        calendar=WorkCalendar(),
    )

    assert result.operations[0].operation_id == "U2-T"
    assert result.operations[0].start == dt(9)
    assert result.operations[1].operation_id == "U1-T"
    assert result.operations[1].start == dt(9, 25)


def test_aggregate_lot_process_forecast_returns_lot_resolution() -> None:
    operations = (
        op("U1-A", "U1", 1, "ASSEMBLY", 10, worker()),
        op("U2-A", "U2", 1, "ASSEMBLY", 10, worker()),
        op("U1-T", "U1", 2, "TUNING", 25, tuning()),
        op("U2-T", "U2", 2, "TUNING", 25, tuning()),
    )
    result = schedule_operations(
        operations=operations,
        dispatch_sequence=("U1-A", "U2-A", "U1-T", "U2-T"),
        resources=resources(),
        calendar=WorkCalendar(),
    )

    forecasts = aggregate_lot_process_forecast(result.operations)
    by_process = {forecast.process_code: forecast for forecast in forecasts}

    assert by_process["ASSEMBLY"].forecast_start == dt(9)
    assert by_process["ASSEMBLY"].forecast_end == dt(9, 10)
    assert by_process["ASSEMBLY"].scheduled_operation_count == 2
    assert by_process["TUNING"].forecast_start == dt(9, 10)
    assert by_process["TUNING"].forecast_end == dt(10)
    assert by_process["TUNING"].scheduled_operation_count == 2


def test_dispatch_sequence_must_cover_every_operation_exactly_once() -> None:
    operations = (
        op("U1-A", "U1", 1, "ASSEMBLY", 10, worker()),
        op("U2-A", "U2", 1, "ASSEMBLY", 10, worker()),
    )

    with pytest.raises(ValueError):
        schedule_operations(
            operations=operations,
            dispatch_sequence=("U1-A",),
            resources=resources(),
            calendar=WorkCalendar(),
        )


def test_repeated_routing_steps_use_execution_sequence_for_precedence() -> None:
    operations = (
        op(
            "U1-T1",
            "U1",
            4,
            "TUNING",
            25,
            tuning(),
            execution_seq=4,
        ),
        op(
            "U1-F1",
            "U1",
            6,
            "FINAL_TEST",
            30,
            worker(),
            execution_seq=6,
        ),
        op(
            "U1-T2",
            "U1",
            4,
            "TUNING",
            25,
            tuning(),
            execution_seq=7,
        ),
        op(
            "U1-F2",
            "U1",
            6,
            "FINAL_TEST",
            30,
            worker(),
            execution_seq=8,
        ),
    )

    result = schedule_operations(
        operations=operations,
        dispatch_sequence=("U1-F2", "U1-T2", "U1-F1", "U1-T1"),
        resources=resources(),
        calendar=WorkCalendar(),
    )

    by_id = {operation.operation_id: operation for operation in result.operations}
    assert by_id["U1-T1"].start == dt(9)
    assert by_id["U1-F1"].start == by_id["U1-T1"].end
    assert by_id["U1-T2"].start == by_id["U1-F1"].end
    assert by_id["U1-F2"].start == by_id["U1-T2"].end
    assert by_id["U1-T2"].step_seq == 4
    assert by_id["U1-T2"].execution_seq == 7
