import pytest

from production_control.core.pace_estimator import (
    PaceBasis,
    estimate_lot_process_work,
    select_pace_minutes_per_unit,
)


def test_uses_standard_pace_when_samples_are_insufficient() -> None:
    pace, basis = select_pace_minutes_per_unit(
        standard_minutes_per_unit=25,
        completed_active_minutes=[20, 40],
        pace_min_samples=3,
    )

    assert pace == 25
    assert basis is PaceBasis.STANDARD


def test_switches_to_actual_average_when_minimum_samples_are_met() -> None:
    forecast = estimate_lot_process_work(
        planned_unit_count=10,
        standard_minutes_per_unit=25,
        completed_active_minutes=[20, 40, 25],
        pace_min_samples=3,
    )

    assert forecast.pace_basis is PaceBasis.ACTUAL_AVERAGE
    assert forecast.pace_minutes_per_unit == pytest.approx(28.3333333333)
    assert forecast.estimated_total_work_minutes == pytest.approx(283.3333333333)
    assert forecast.cumulative_actual_active_minutes == 85
    assert forecast.remaining_normal_work_minutes == pytest.approx(198.3333333333)
    assert forecast.remaining_work_minutes == pytest.approx(198.3333333333)


def test_adds_confirmed_rework_on_top_of_remaining_normal_work() -> None:
    forecast = estimate_lot_process_work(
        planned_unit_count=10,
        standard_minutes_per_unit=25,
        completed_active_minutes=[20, 40, 25],
        pace_min_samples=3,
        confirmed_rework_work_minutes=55,
    )

    assert forecast.remaining_normal_work_minutes == pytest.approx(198.3333333333)
    assert forecast.remaining_work_minutes == pytest.approx(253.3333333333)


def test_running_active_time_can_be_included_without_changing_pace_sample() -> None:
    forecast = estimate_lot_process_work(
        planned_unit_count=10,
        standard_minutes_per_unit=25,
        completed_active_minutes=[20, 40, 25],
        pace_min_samples=3,
        cumulative_actual_active_minutes=100,
    )

    assert forecast.completed_sample_count == 3
    assert forecast.pace_minutes_per_unit == pytest.approx(28.3333333333)
    assert forecast.remaining_normal_work_minutes == pytest.approx(183.3333333333)


def test_rejects_invalid_policy_inputs() -> None:
    with pytest.raises(ValueError):
        select_pace_minutes_per_unit(
            standard_minutes_per_unit=0,
            completed_active_minutes=[],
            pace_min_samples=3,
        )

    with pytest.raises(ValueError):
        select_pace_minutes_per_unit(
            standard_minutes_per_unit=25,
            completed_active_minutes=[20, -1],
            pace_min_samples=3,
        )


def test_preserves_signed_budget_overrun_instead_of_hiding_it() -> None:
    forecast = estimate_lot_process_work(
        planned_unit_count=10,
        standard_minutes_per_unit=25,
        completed_active_minutes=[20, 40],
        pace_min_samples=3,
        cumulative_actual_active_minutes=260,
    )

    assert forecast.estimated_total_work_minutes == 250
    assert forecast.work_budget_balance_minutes == -10
    assert forecast.overrun_minutes == 10
    assert forecast.remaining_normal_work_minutes == 0


def test_positive_budget_balance_has_no_overrun() -> None:
    forecast = estimate_lot_process_work(
        planned_unit_count=10,
        standard_minutes_per_unit=25,
        completed_active_minutes=[20],
        pace_min_samples=3,
    )

    assert forecast.work_budget_balance_minutes == 230
    assert forecast.overrun_minutes == 0
    assert forecast.remaining_normal_work_minutes == 230
