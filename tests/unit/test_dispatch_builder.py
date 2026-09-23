from datetime import datetime
from zoneinfo import ZoneInfo

import pytest

from production_control.core.dispatch_builder import (
    OperationDispatchInput,
    build_dispatch_sequence,
)
from production_control.core.priority_rules import LotPriorityInput, PriorityRule
from production_control.domain.enums import OperationState

SEOUL = ZoneInfo("Asia/Seoul")


def dt(hour: int, minute: int = 0) -> datetime:
    return datetime(2026, 10, 5, hour, minute, tzinfo=SEOUL)


def lot(
    lot_id: str,
    release_hour: int,
    deadline_hour: int,
) -> LotPriorityInput:
    return LotPriorityInput(
        lot_id=lot_id,
        release_at=dt(release_hour),
        deadline=dt(deadline_hour),
        remaining_work_minutes=60,
        time_until_deadline_minutes=180,
    )


def operation(
    operation_id: str,
    lot_id: str,
    unit_id: str,
    state: OperationState,
    eligible_hour: int = 9,
    eligible_minute: int = 0,
) -> OperationDispatchInput:
    return OperationDispatchInput(
        operation_id=operation_id,
        lot_id=lot_id,
        unit_id=unit_id,
        state=state,
        eligible_at=dt(eligible_hour, eligible_minute),
    )


def test_lot_priority_is_applied_before_same_lot_tie_break() -> None:
    sequence = build_dispatch_sequence(
        lots=(lot("LATE_RELEASE", 10, 11), lot("EARLY_RELEASE", 9, 15)),
        operations=(
            operation("OP-LATE", "LATE_RELEASE", "U01", OperationState.WAITING),
            operation("OP-EARLY", "EARLY_RELEASE", "U01", OperationState.WAITING),
        ),
        rule=PriorityRule.FCFS,
    )

    assert sequence == ("OP-EARLY", "OP-LATE")


def test_same_lot_state_order_is_running_waiting_hold() -> None:
    sequence = build_dispatch_sequence(
        lots=(lot("LOT-01", 9, 15),),
        operations=(
            operation("HOLD", "LOT-01", "U03", OperationState.HOLD),
            operation("WAIT", "LOT-01", "U02", OperationState.WAITING),
            operation("RUN", "LOT-01", "U01", OperationState.RUNNING),
        ),
        rule=PriorityRule.EDD,
    )

    assert sequence == ("RUN", "WAIT", "HOLD")


def test_same_state_uses_eligible_at_then_unit_id() -> None:
    sequence = build_dispatch_sequence(
        lots=(lot("LOT-01", 9, 15),),
        operations=(
            operation("U03", "LOT-01", "U03", OperationState.WAITING, 9, 10),
            operation("U02", "LOT-01", "U02", OperationState.WAITING, 9),
            operation("U01", "LOT-01", "U01", OperationState.WAITING, 9),
        ),
        rule=PriorityRule.EDD,
    )

    assert sequence == ("U01", "U02", "U03")


def test_exact_same_lot_tie_preserves_input_order() -> None:
    sequence = build_dispatch_sequence(
        lots=(lot("LOT-01", 9, 15),),
        operations=(
            operation("FIRST", "LOT-01", "U01", OperationState.WAITING),
            operation("SECOND", "LOT-01", "U01", OperationState.WAITING),
        ),
        rule=PriorityRule.EDD,
    )

    assert sequence == ("FIRST", "SECOND")


def test_completed_operation_is_rejected() -> None:
    with pytest.raises(ValueError):
        operation("DONE", "LOT-01", "U01", OperationState.COMPLETED)


def test_operation_with_missing_priority_lot_is_rejected() -> None:
    with pytest.raises(ValueError):
        build_dispatch_sequence(
            lots=(lot("LOT-01", 9, 15),),
            operations=(
                operation("UNKNOWN", "LOT-02", "U01", OperationState.WAITING),
            ),
            rule=PriorityRule.FCFS,
        )
