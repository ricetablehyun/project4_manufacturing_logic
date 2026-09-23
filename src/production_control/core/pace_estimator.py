"""LOT × process pace estimation for live production forecasting.

V1 policy:
- Start from a human-entered standard minutes/unit value.
- Once enough completed Unit samples exist, switch to the mean active time of
  completed normal attempts for that LOT × process.
- Remaining work is evaluated at LOT × process level, while Unit records remain
  the execution-history source.
- The signed work-budget balance is preserved so time overruns are not hidden by
  clamping scheduler-facing remaining work to zero.
"""

from collections.abc import Sequence
from dataclasses import dataclass
from enum import StrEnum
from statistics import fmean


class PaceBasis(StrEnum):
    """Source used for the current minutes-per-unit pace."""

    STANDARD = "STANDARD"
    ACTUAL_AVERAGE = "ACTUAL_AVERAGE"


@dataclass(frozen=True, slots=True)
class PaceForecast:
    """Calculated work forecast for one LOT × process."""

    pace_minutes_per_unit: float
    pace_basis: PaceBasis
    completed_sample_count: int
    estimated_total_work_minutes: float
    cumulative_actual_active_minutes: float
    work_budget_balance_minutes: float
    overrun_minutes: float
    remaining_normal_work_minutes: float
    confirmed_rework_work_minutes: float
    remaining_work_minutes: float


def select_pace_minutes_per_unit(
    *,
    standard_minutes_per_unit: float,
    completed_active_minutes: Sequence[float],
    pace_min_samples: int,
) -> tuple[float, PaceBasis]:
    """Select Standard or Actual Average pace according to the V1 policy."""

    if standard_minutes_per_unit <= 0:
        raise ValueError("standard_minutes_per_unit must be greater than 0")
    if pace_min_samples <= 0:
        raise ValueError("pace_min_samples must be greater than 0")
    if any(minutes <= 0 for minutes in completed_active_minutes):
        raise ValueError("completed_active_minutes must contain only positive values")

    if len(completed_active_minutes) < pace_min_samples:
        return float(standard_minutes_per_unit), PaceBasis.STANDARD

    return float(fmean(completed_active_minutes)), PaceBasis.ACTUAL_AVERAGE


def estimate_lot_process_work(
    *,
    planned_unit_count: int,
    standard_minutes_per_unit: float,
    completed_active_minutes: Sequence[float],
    pace_min_samples: int,
    cumulative_actual_active_minutes: float | None = None,
    confirmed_rework_work_minutes: float = 0.0,
) -> PaceForecast:
    """Estimate remaining work for one LOT × process.

    completed_active_minutes estimates the pace. The cumulative actual value
    can additionally include active time already spent on a RUNNING Unit.
    """

    if planned_unit_count < 0:
        raise ValueError("planned_unit_count must be 0 or greater")
    if confirmed_rework_work_minutes < 0:
        raise ValueError("confirmed_rework_work_minutes must be 0 or greater")

    pace, basis = select_pace_minutes_per_unit(
        standard_minutes_per_unit=standard_minutes_per_unit,
        completed_active_minutes=completed_active_minutes,
        pace_min_samples=pace_min_samples,
    )

    actual_active = (
        float(sum(completed_active_minutes))
        if cumulative_actual_active_minutes is None
        else float(cumulative_actual_active_minutes)
    )
    if actual_active < 0:
        raise ValueError("cumulative_actual_active_minutes must be 0 or greater")

    estimated_total = pace * planned_unit_count
    work_budget_balance = estimated_total - actual_active
    overrun = max(-work_budget_balance, 0.0)
    remaining_normal = max(work_budget_balance, 0.0)
    remaining_total = remaining_normal + confirmed_rework_work_minutes

    return PaceForecast(
        pace_minutes_per_unit=pace,
        pace_basis=basis,
        completed_sample_count=len(completed_active_minutes),
        estimated_total_work_minutes=estimated_total,
        cumulative_actual_active_minutes=actual_active,
        work_budget_balance_minutes=work_budget_balance,
        overrun_minutes=overrun,
        remaining_normal_work_minutes=remaining_normal,
        confirmed_rework_work_minutes=float(confirmed_rework_work_minutes),
        remaining_work_minutes=remaining_total,
    )
