import math

import pytest

from production_control.core.pace_estimator import estimate_lot_process_work
from production_control.core.pace_workload import (
    UnitWorkloadChunk,
    distribute_remaining_normal_work,
)


def test_distributes_remaining_work_equally() -> None:
    chunks = distribute_remaining_normal_work(
        remaining_normal_work_minutes=198,
        unfinished_unit_ids=("U04", "U05", "U06"),
    )

    assert [chunk.workload_minutes for chunk in chunks] == [66, 66, 66]


def test_preserves_input_unit_order() -> None:
    chunks = distribute_remaining_normal_work(
        remaining_normal_work_minutes=90,
        unfinished_unit_ids=("U09", "U03", "U07"),
    )

    assert [chunk.unit_id for chunk in chunks] == ["U09", "U03", "U07"]


def test_fractional_chunks_preserve_total_with_float_tolerance() -> None:
    chunks = distribute_remaining_normal_work(
        remaining_normal_work_minutes=198.3333333333,
        unfinished_unit_ids=("U04", "U05", "U06", "U07", "U08", "U09", "U10"),
    )

    assert sum(chunk.workload_minutes for chunk in chunks) == pytest.approx(
        198.3333333333
    )
    assert len({chunk.workload_minutes for chunk in chunks}) == 1


def test_zero_work_with_no_unfinished_units_returns_empty() -> None:
    assert (
        distribute_remaining_normal_work(
            remaining_normal_work_minutes=0,
            unfinished_unit_ids=(),
        )
        == ()
    )


def test_zero_work_with_unfinished_units_returns_zero_chunks() -> None:
    chunks = distribute_remaining_normal_work(
        remaining_normal_work_minutes=0,
        unfinished_unit_ids=("U01", "U02"),
    )

    assert chunks == (
        UnitWorkloadChunk("U01", 0),
        UnitWorkloadChunk("U02", 0),
    )


def test_positive_work_without_unfinished_units_is_rejected() -> None:
    with pytest.raises(ValueError):
        distribute_remaining_normal_work(
            remaining_normal_work_minutes=30,
            unfinished_unit_ids=(),
        )


def test_invalid_workload_and_unit_ids_are_rejected() -> None:
    for invalid in (-1, math.inf, math.nan):
        with pytest.raises(ValueError):
            distribute_remaining_normal_work(
                remaining_normal_work_minutes=invalid,
                unfinished_unit_ids=("U01",),
            )

    with pytest.raises(ValueError):
        distribute_remaining_normal_work(
            remaining_normal_work_minutes=30,
            unfinished_unit_ids=("U01", "U01"),
        )

    with pytest.raises(ValueError):
        distribute_remaining_normal_work(
            remaining_normal_work_minutes=30,
            unfinished_unit_ids=("U01", ""),
        )


@pytest.mark.parametrize(
    ("completed_minutes", "expected_chunk"),
    [
        (30, 220 / 9),
        (20, 230 / 9),
    ],
)
def test_rolling_redistribution_reflects_overrun_or_saved_time(
    completed_minutes: float,
    expected_chunk: float,
) -> None:
    forecast = estimate_lot_process_work(
        planned_unit_count=10,
        standard_minutes_per_unit=25,
        completed_active_minutes=[completed_minutes],
        pace_min_samples=3,
    )

    chunks = distribute_remaining_normal_work(
        remaining_normal_work_minutes=forecast.remaining_normal_work_minutes,
        unfinished_unit_ids=tuple(f"U{index:02d}" for index in range(2, 11)),
    )

    assert all(
        chunk.workload_minutes == pytest.approx(expected_chunk)
        for chunk in chunks
    )


def test_updated_actual_average_pace_recalculates_total_budget_before_distribution() -> None:
    forecast = estimate_lot_process_work(
        planned_unit_count=10,
        standard_minutes_per_unit=25,
        completed_active_minutes=[20, 30, 28],
        pace_min_samples=3,
    )

    chunks = distribute_remaining_normal_work(
        remaining_normal_work_minutes=forecast.remaining_normal_work_minutes,
        unfinished_unit_ids=("U04", "U05", "U06", "U07", "U08", "U09", "U10"),
    )

    assert forecast.pace_minutes_per_unit == 26
    assert forecast.estimated_total_work_minutes == 260
    assert forecast.cumulative_actual_active_minutes == 78
    assert all(chunk.workload_minutes == pytest.approx(26) for chunk in chunks)
