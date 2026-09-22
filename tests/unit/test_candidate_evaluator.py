import pytest

from production_control.core.candidate_evaluator import (
    CandidateKPI,
    PriorityRankSnapshot,
    count_priority_rank_changes,
    select_candidate,
)


def candidate(
    candidate_id: str,
    *,
    late: int,
    tardiness: float,
    overtime: float,
    changes: int,
) -> CandidateKPI:
    return CandidateKPI(
        candidate_id=candidate_id,
        late_lot_count=late,
        total_tardiness_minutes=tardiness,
        overtime_minutes=overtime,
        change_count=changes,
    )


def test_late_lot_count_is_first_comparison_level() -> None:
    chosen = select_candidate(
        (
            candidate("A", late=1, tardiness=500, overtime=0, changes=0),
            candidate("B", late=2, tardiness=0, overtime=0, changes=0),
        )
    )

    assert chosen.candidate_id == "A"


def test_tardiness_is_second_comparison_level() -> None:
    chosen = select_candidate(
        (
            candidate("A", late=1, tardiness=100, overtime=1000, changes=99),
            candidate("B", late=1, tardiness=120, overtime=0, changes=0),
        )
    )

    assert chosen.candidate_id == "A"


def test_overtime_is_third_comparison_level() -> None:
    chosen = select_candidate(
        (
            candidate("A", late=1, tardiness=100, overtime=60, changes=99),
            candidate("B", late=1, tardiness=100, overtime=120, changes=0),
        )
    )

    assert chosen.candidate_id == "A"


def test_change_count_is_fourth_comparison_level() -> None:
    chosen = select_candidate(
        (
            candidate("A", late=1, tardiness=100, overtime=60, changes=2),
            candidate("B", late=1, tardiness=100, overtime=60, changes=3),
        )
    )

    assert chosen.candidate_id == "A"


def test_exact_kpi_tie_preserves_candidate_input_order() -> None:
    chosen = select_candidate(
        (
            candidate("FIRST", late=1, tardiness=100, overtime=60, changes=2),
            candidate("SECOND", late=1, tardiness=100, overtime=60, changes=2),
        )
    )

    assert chosen.candidate_id == "FIRST"


def test_change_count_ignores_frozen_tasks() -> None:
    approved = (
        PriorityRankSnapshot("LOT-A", "TUNING", 1, frozen=False),
        PriorityRankSnapshot("LOT-B", "TUNING", 2, frozen=True),
    )
    proposed = (
        PriorityRankSnapshot("LOT-A", "TUNING", 2, frozen=False),
        PriorityRankSnapshot("LOT-B", "TUNING", 1, frozen=True),
    )

    assert count_priority_rank_changes(approved=approved, candidate=proposed) == 1


def test_priority_snapshot_sets_must_match() -> None:
    with pytest.raises(ValueError):
        count_priority_rank_changes(
            approved=(PriorityRankSnapshot("LOT-A", "TUNING", 1),),
            candidate=(PriorityRankSnapshot("LOT-B", "TUNING", 1),),
        )


def test_empty_candidate_set_is_rejected() -> None:
    with pytest.raises(ValueError):
        select_candidate(())
