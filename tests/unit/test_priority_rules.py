from datetime import datetime
from zoneinfo import ZoneInfo

import pytest

from production_control.core.priority_rules import (
    LotPriorityInput,
    PriorityRule,
    rank_lots,
    resolve_deadline,
)

SEOUL = ZoneInfo("Asia/Seoul")


def dt(hour: int, minute: int = 0) -> datetime:
    return datetime(2026, 10, 5, hour, minute, tzinfo=SEOUL)


def fixture_lots() -> tuple[LotPriorityInput, ...]:
    return (
        LotPriorityInput("LOT-A", dt(8), dt(15), 60, 360),
        LotPriorityInput("LOT-B", dt(8, 15), dt(12, 30), 150, 210),
        LotPriorityInput("LOT-C", dt(8, 30), dt(11, 15), 90, 135),
        LotPriorityInput("LOT-D", dt(8, 45), dt(12), 40, 180),
    )


@pytest.mark.parametrize(
    ("rule", "expected"),
    [
        (PriorityRule.FCFS, ("LOT-A", "LOT-B", "LOT-C", "LOT-D")),
        (PriorityRule.EDD, ("LOT-C", "LOT-D", "LOT-B", "LOT-A")),
        (PriorityRule.SLACK, ("LOT-C", "LOT-B", "LOT-D", "LOT-A")),
        (PriorityRule.CR, ("LOT-B", "LOT-C", "LOT-D", "LOT-A")),
    ],
)
def test_f01_priority_orders(rule: PriorityRule, expected: tuple[str, ...]) -> None:
    ranked = rank_lots(fixture_lots(), rule=rule)

    assert tuple(lot.lot_id for lot in ranked) == expected


def test_f01_slack_and_cr_values_match_design_fixture() -> None:
    by_id = {lot.lot_id: lot for lot in fixture_lots()}

    assert by_id["LOT-A"].slack_minutes == 300
    assert by_id["LOT-A"].critical_ratio == 6
    assert by_id["LOT-B"].slack_minutes == 60
    assert by_id["LOT-B"].critical_ratio == pytest.approx(1.4)
    assert by_id["LOT-C"].slack_minutes == 45
    assert by_id["LOT-C"].critical_ratio == pytest.approx(1.5)
    assert by_id["LOT-D"].slack_minutes == 140
    assert by_id["LOT-D"].critical_ratio == pytest.approx(4.5)


def test_deadline_prefers_next_relevant_gate() -> None:
    assert resolve_deadline(
        next_relevant_gate_at=dt(12),
        final_due_at=dt(17),
    ) == dt(12)


def test_deadline_falls_back_to_final_due() -> None:
    assert resolve_deadline(
        next_relevant_gate_at=None,
        final_due_at=dt(17),
    ) == dt(17)


def test_exact_priority_tie_preserves_input_order() -> None:
    first = LotPriorityInput("FIRST", dt(9), dt(12), 60, 180)
    second = LotPriorityInput("SECOND", dt(9), dt(12), 60, 180)

    ranked = rank_lots((first, second), rule=PriorityRule.SLACK)

    assert tuple(lot.lot_id for lot in ranked) == ("FIRST", "SECOND")


def test_active_lot_requires_positive_remaining_work() -> None:
    with pytest.raises(ValueError):
        LotPriorityInput("LOT-X", dt(9), dt(12), 0, 180)
