"""Replanning candidate KPI calculation and lexicographic comparison."""

from collections.abc import Iterable
from dataclasses import dataclass
from math import isfinite


@dataclass(frozen=True, slots=True)
class CandidateKPI:
    """Confirmed V1 candidate-comparison metrics."""

    candidate_id: str
    late_lot_count: int
    total_tardiness_minutes: float
    overtime_minutes: float
    change_count: int

    def __post_init__(self) -> None:
        if not self.candidate_id:
            raise ValueError("candidate_id must not be empty")
        if self.late_lot_count < 0:
            raise ValueError("late_lot_count must be 0 or greater")
        if self.change_count < 0:
            raise ValueError("change_count must be 0 or greater")
        for name, value in (
            ("total_tardiness_minutes", self.total_tardiness_minutes),
            ("overtime_minutes", self.overtime_minutes),
        ):
            if value < 0 or not isfinite(value):
                raise ValueError(f"{name} must be finite and 0 or greater")

    @property
    def comparison_key(self) -> tuple[int, float, float, int]:
        """D029 lexicographic comparison order."""

        return (
            self.late_lot_count,
            self.total_tardiness_minutes,
            self.overtime_minutes,
            self.change_count,
        )


@dataclass(frozen=True, slots=True)
class PriorityRankSnapshot:
    """LOT x process priority snapshot used for change_count."""

    lot_id: str
    process_code: str
    priority_rank: int
    frozen: bool = False

    def __post_init__(self) -> None:
        if not self.lot_id:
            raise ValueError("lot_id must not be empty")
        if not self.process_code:
            raise ValueError("process_code must not be empty")
        if self.priority_rank <= 0:
            raise ValueError("priority_rank must be greater than 0")


def count_priority_rank_changes(
    *,
    approved: Iterable[PriorityRankSnapshot],
    candidate: Iterable[PriorityRankSnapshot],
) -> int:
    """Count changed LOT x process ranks outside the Frozen Horizon."""

    approved_map = {
        (item.lot_id, item.process_code): item
        for item in approved
    }
    candidate_map = {
        (item.lot_id, item.process_code): item
        for item in candidate
    }

    if approved_map.keys() != candidate_map.keys():
        raise ValueError("approved and candidate priority snapshots must cover the same tasks")

    changed = 0
    for key, approved_item in approved_map.items():
        candidate_item = candidate_map[key]
        if approved_item.frozen:
            continue
        if approved_item.priority_rank != candidate_item.priority_rank:
            changed += 1

    return changed


def select_candidate(
    candidates: Iterable[CandidateKPI],
) -> CandidateKPI:
    """Return the lexicographically best candidate.

    Exact KPI ties preserve caller order; no additional hidden preference is
    introduced.
    """

    candidate_list = list(candidates)
    if not candidate_list:
        raise ValueError("at least one candidate is required")

    return min(candidate_list, key=lambda candidate: candidate.comparison_key)
