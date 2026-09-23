"""Distribute LOT x process remaining normal work into Unit scheduling chunks.

The chunks are not predictions of individual Unit duration. They are equal
shares of the confirmed LOT x process remaining normal workload so the existing
Unit-level scheduler can preserve routing, WIP-buffer, and Resource constraints.
Confirmed rework remains outside this normal-work distribution.
"""

from collections.abc import Sequence
from dataclasses import dataclass
from math import isfinite


@dataclass(frozen=True, slots=True)
class UnitWorkloadChunk:
    """One calculation-only share of LOT x process remaining normal work."""

    unit_id: str
    workload_minutes: float

    def __post_init__(self) -> None:
        if not self.unit_id:
            raise ValueError("unit_id must not be empty")
        if self.workload_minutes < 0 or not isfinite(self.workload_minutes):
            raise ValueError("workload_minutes must be finite and 0 or greater")


def distribute_remaining_normal_work(
    *,
    remaining_normal_work_minutes: float,
    unfinished_unit_ids: Sequence[str],
) -> tuple[UnitWorkloadChunk, ...]:
    """Split remaining normal work equally across unfinished normal Units.

    This implements D040. The returned workload is a scheduling calculation
    share, not an estimate that a specific Unit will actually take that long.
    """

    if (
        remaining_normal_work_minutes < 0
        or not isfinite(remaining_normal_work_minutes)
    ):
        raise ValueError(
            "remaining_normal_work_minutes must be finite and 0 or greater"
        )

    unit_ids = tuple(unfinished_unit_ids)
    if any(not unit_id for unit_id in unit_ids):
        raise ValueError("unfinished_unit_ids must not contain empty values")
    if len(unit_ids) != len(set(unit_ids)):
        raise ValueError("unfinished_unit_ids must be unique")

    if not unit_ids:
        if remaining_normal_work_minutes == 0:
            return ()
        raise ValueError("positive remaining normal work requires unfinished Units")

    chunk_minutes = remaining_normal_work_minutes / len(unit_ids)
    return tuple(
        UnitWorkloadChunk(
            unit_id=unit_id,
            workload_minutes=chunk_minutes,
        )
        for unit_id in unit_ids
    )
