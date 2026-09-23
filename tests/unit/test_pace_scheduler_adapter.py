from datetime import datetime
from zoneinfo import ZoneInfo

import pytest

from production_control.core.pace_estimator import estimate_lot_process_work
from production_control.core.pace_scheduler_adapter import (
    ForecastReadiness,
    HoldDurationBasis,
    UnitPaceSchedulingInput,
    build_pace_schedule_inputs,
    resume_held_unit,
)
from production_control.core.slot_engine import ResourceRequirement
from production_control.domain.enums import OperationState

SEOUL = ZoneInfo("Asia/Seoul")


def dt(hour: int, minute: int = 0) -> datetime:
    return datetime(2026, 10, 5, hour, minute, tzinfo=SEOUL)


def forecast(
    *,
    completed: list[float] | None = None,
    cumulative_actual: float | None = None,
):
    return estimate_lot_process_work(
        planned_unit_count=4,
        standard_minutes_per_unit=25,
        completed_active_minutes=completed or [],
        pace_min_samples=3,
        cumulative_actual_active_minutes=cumulative_actual,
    )


def unit(
    operation_id: str,
    unit_id: str,
    *,
    state: OperationState = OperationState.WAITING,
    active_minutes: float = 0,
    expected_remaining_minutes: float | None = None,
    lot_id: str = "LOT-A",
    process_code: str = "TUNING",
    step_seq: int = 1,
    hold_remaining_minutes: float | None = None,
    standard_minutes_per_unit: float | None = None,
    eligible_at: datetime | None = None,
    release_at: datetime | None = None,
) -> UnitPaceSchedulingInput:
    return UnitPaceSchedulingInput(
        operation_id=operation_id,
        lot_id=lot_id,
        unit_id=unit_id,
        step_seq=step_seq,
        process_code=process_code,
        state=state,
        eligible_at=eligible_at or dt(9),
        release_at=release_at or dt(9),
        requirements=(ResourceRequirement("TUNING_STATION"),),
        active_minutes=active_minutes,
        expected_remaining_minutes=expected_remaining_minutes,
        hold_remaining_minutes=hold_remaining_minutes,
        standard_minutes_per_unit=standard_minutes_per_unit,
    )


def test_builds_equal_scheduler_chunks_for_unfinished_units() -> None:
    result = build_pace_schedule_inputs(
        forecast=forecast(completed=[20]),
        units=(
            unit("OP-2", "U02"),
            unit("OP-3", "U03"),
            unit("OP-4", "U04"),
        ),
    )

    assert result.readiness is ForecastReadiness.READY
    assert [item.operation.duration_minutes for item in result.items] == [
        pytest.approx(80 / 3),
        pytest.approx(80 / 3),
        pytest.approx(80 / 3),
    ]


def test_running_unit_over_pace_waits_for_worker_estimate() -> None:
    result = build_pace_schedule_inputs(
        forecast=forecast(cumulative_actual=31),
        units=(
            unit(
                "OP-1",
                "U01",
                state=OperationState.RUNNING,
                active_minutes=31,
            ),
            unit("OP-2", "U02"),
            unit("OP-3", "U03"),
            unit("OP-4", "U04"),
        ),
    )

    assert result.readiness is ForecastReadiness.WAIT
    assert result.items == ()
    assert result.waiting_operation_ids == ("OP-1",)
    assert result.signals[0].pace_overrun_minutes == 6


def test_worker_estimate_overrides_running_overrun_chunk() -> None:
    result = build_pace_schedule_inputs(
        forecast=forecast(cumulative_actual=31),
        units=(
            unit(
                "OP-1",
                "U01",
                state=OperationState.RUNNING,
                active_minutes=31,
                expected_remaining_minutes=15,
            ),
            unit("OP-2", "U02"),
            unit("OP-3", "U03"),
            unit("OP-4", "U04"),
        ),
    )

    assert result.readiness is ForecastReadiness.READY
    by_id = {item.operation.operation_id: item for item in result.items}
    assert by_id["OP-1"].operation.duration_minutes == 15
    assert by_id["OP-2"].operation.duration_minutes == pytest.approx(69 / 4)


def test_running_unit_below_pace_uses_rolling_chunk() -> None:
    result = build_pace_schedule_inputs(
        forecast=forecast(cumulative_actual=18),
        units=(
            unit(
                "OP-1",
                "U01",
                state=OperationState.RUNNING,
                active_minutes=18,
            ),
            unit("OP-2", "U02"),
            unit("OP-3", "U03"),
            unit("OP-4", "U04"),
        ),
    )

    assert result.readiness is ForecastReadiness.READY
    assert result.items[0].operation.duration_minutes == pytest.approx(82 / 4)
    assert result.signals[0].pace_overrun_minutes == 0


def test_exhausted_budget_with_unfinished_units_stays_wait() -> None:
    result = build_pace_schedule_inputs(
        forecast=forecast(cumulative_actual=100),
        units=(
            unit("OP-1", "U01"),
            unit("OP-2", "U02"),
        ),
    )

    assert result.readiness is ForecastReadiness.WAIT
    assert result.items == ()
    assert result.waiting_operation_ids == ("OP-1", "OP-2")


def test_no_unfinished_units_and_zero_remaining_work_is_ready() -> None:
    result = build_pace_schedule_inputs(
        forecast=forecast(cumulative_actual=100),
        units=(),
    )

    assert result.readiness is ForecastReadiness.READY
    assert result.items == ()


def test_completed_units_are_rejected() -> None:
    with pytest.raises(ValueError):
        unit(
            "OP-1",
            "U01",
            state=OperationState.COMPLETED,
        )


def test_adapter_requires_one_lot_process_group() -> None:
    with pytest.raises(ValueError):
        build_pace_schedule_inputs(
            forecast=forecast(),
            units=(
                unit("OP-1", "U01"),
                unit("OP-2", "U02", lot_id="LOT-B"),
            ),
        )


def test_hold_uses_manager_remaining_override() -> None:
    result = build_pace_schedule_inputs(
        forecast=forecast(),
        units=(
            unit(
                "OP-1",
                "U01",
                state=OperationState.HOLD,
                hold_remaining_minutes=12,
                standard_minutes_per_unit=25,
            ),
        ),
    )

    assert result.readiness is ForecastReadiness.READY
    assert result.items[0].operation.duration_minutes == 12
    assert result.signals[0].hold_forecast_minutes == 12
    assert (
        result.signals[0].hold_duration_basis
        is HoldDurationBasis.MANAGER_OVERRIDE
    )


def test_hold_without_override_uses_standard_fallback() -> None:
    result = build_pace_schedule_inputs(
        forecast=forecast(),
        units=(
            unit(
                "OP-1",
                "U01",
                state=OperationState.HOLD,
                standard_minutes_per_unit=25,
            ),
        ),
    )

    assert result.readiness is ForecastReadiness.READY
    assert result.items[0].operation.duration_minutes == 25
    assert result.signals[0].hold_forecast_minutes == 25
    assert (
        result.signals[0].hold_duration_basis
        is HoldDurationBasis.STANDARD_FALLBACK
    )


def test_hold_without_override_or_standard_is_rejected() -> None:
    with pytest.raises(ValueError):
        build_pace_schedule_inputs(
            forecast=forecast(),
            units=(
                unit(
                    "OP-1",
                    "U01",
                    state=OperationState.HOLD,
                ),
            ),
        )


def test_invalid_hold_standard_is_rejected() -> None:
    with pytest.raises(ValueError):
        unit(
            "OP-1",
            "U01",
            state=OperationState.HOLD,
            standard_minutes_per_unit=0,
        )


def test_resume_changes_hold_to_running_and_releases_at_resume_time() -> None:
    held = unit(
        "OP-1",
        "U01",
        state=OperationState.HOLD,
        hold_remaining_minutes=12,
    )

    resumed = resume_held_unit(
        unit=held,
        resumed_at=dt(10),
    )

    assert resumed.state is OperationState.RUNNING
    assert resumed.eligible_at == dt(10)
    assert resumed.release_at == dt(10)


def test_resume_preserves_later_existing_release_constraints() -> None:
    held = unit(
        "OP-1",
        "U01",
        state=OperationState.HOLD,
        hold_remaining_minutes=12,
        eligible_at=dt(11),
        release_at=dt(12),
    )

    resumed = resume_held_unit(
        unit=held,
        resumed_at=dt(10),
    )

    assert resumed.eligible_at == dt(11)
    assert resumed.release_at == dt(12)


def test_only_hold_state_can_be_resumed() -> None:
    with pytest.raises(ValueError):
        resume_held_unit(
            unit=unit("OP-1", "U01", state=OperationState.WAITING),
            resumed_at=dt(10),
        )


def test_resumed_running_over_pace_still_requires_worker_residual() -> None:
    held = unit(
        "OP-1",
        "U01",
        state=OperationState.HOLD,
        active_minutes=31,
        hold_remaining_minutes=12,
    )
    resumed = resume_held_unit(
        unit=held,
        resumed_at=dt(10),
    )

    result = build_pace_schedule_inputs(
        forecast=forecast(cumulative_actual=31),
        units=(resumed,),
    )

    assert result.readiness is ForecastReadiness.WAIT
    assert result.waiting_operation_ids == ("OP-1",)
    assert result.signals[0].pace_overrun_minutes == 6
