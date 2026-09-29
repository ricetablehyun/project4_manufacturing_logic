from datetime import datetime
from zoneinfo import ZoneInfo

import pytest

from production_control.ui.operator_model import (
    allowed_event_types,
    current_operation_for_unit,
    default_event_time,
    latest_execution_reference,
    reason_required,
)

SEOUL = ZoneInfo("Asia/Seoul")


def dt(hour: int, minute: int = 0) -> datetime:
    return datetime(2026, 10, 5, hour, minute, tzinfo=SEOUL)


def test_current_operation_uses_earliest_incomplete_step() -> None:
    operations = [
        {"lot_id": "LOT-101", "unit_id": "U1", "seq_no": 1, "state": "COMPLETED"},
        {"lot_id": "LOT-101", "unit_id": "U1", "seq_no": 4, "state": "WAITING"},
        {"lot_id": "LOT-101", "unit_id": "U1", "seq_no": 3, "state": "WAITING"},
    ]

    selected = current_operation_for_unit(operations, lot_id="LOT-101", unit_id="U1")

    assert selected is operations[2]


@pytest.mark.parametrize(
    ("state", "process_code", "result", "expected"),
    [
        ("WAITING", "TUNING", None, ("START",)),
        ("RUNNING", "TUNING", None, ("HOLD", "COMPLETE")),
        ("RUNNING", "FINAL_TEST", None, ("HOLD", "PASS", "FAIL")),
        ("HOLD", "TUNING", None, ("RESUME",)),
        ("COMPLETED", "FINAL_TEST", None, ("PASS", "FAIL")),
        ("COMPLETED", "FINAL_TEST", "PASS", ()),
    ],
)
def test_allowed_event_types_follow_execution_state(
    state: str,
    process_code: str,
    result: str | None,
    expected: tuple[str, ...],
) -> None:
    assert allowed_event_types(
        {"state": state, "process_code": process_code, "result": result}
    ) == expected


def test_reason_is_required_only_for_hold_and_final_test_fail() -> None:
    assert reason_required(event_type="HOLD", process_code="TUNING")
    assert reason_required(event_type="FAIL", process_code="FINAL_TEST")
    assert not reason_required(event_type="FAIL", process_code="TUNING")
    assert not reason_required(event_type="COMPLETE", process_code="TUNING")


def test_default_event_time_uses_last_event_plus_ten_minutes() -> None:
    operation = {
        "last_event_at": dt(9).isoformat(),
        "eligible_at": dt(8).isoformat(),
    }

    assert default_event_time(operation) == dt(9, 10)


def test_latest_execution_reference_never_predates_latest_event() -> None:
    operations = [
        {"last_event_at": dt(9).isoformat()},
        {"last_event_at": dt(11, 30).isoformat()},
    ]

    assert latest_execution_reference(operations, now=dt(10)) == dt(11, 30)
    assert latest_execution_reference(operations, now=dt(12)) == dt(12)
