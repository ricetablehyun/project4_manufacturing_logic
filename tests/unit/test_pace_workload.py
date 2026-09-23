import math

import pytest

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
