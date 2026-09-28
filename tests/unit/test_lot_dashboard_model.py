from datetime import datetime
from zoneinfo import ZoneInfo

import pytest

from production_control.ui.lot_dashboard_model import (
    build_lot_progress,
    build_process_status_rows,
    build_process_unit_rows,
    build_unit_detail_rows,
    format_duration_minutes,
    minimum_gate_slack,
    shipping_inspection_expected_finish,
)

SEOUL = ZoneInfo("Asia/Seoul")


def operation(
    *,
    lot_id: str = "LOT-101",
    unit_id: str,
    unit_code: str,
    seq_no: int,
    process_code: str,
    state: str,
    active_minutes: float = 0.0,
    result: str | None = None,
) -> dict[str, object]:
    return {
        "lot_id": lot_id,
        "unit_id": unit_id,
        "unit_code": unit_code,
        "seq_no": seq_no,
        "process_code": process_code,
        "state": state,
        "attempt_no": 1,
        "active_minutes": active_minutes,
        "result": result,
    }


def test_build_lot_progress_returns_completion_per_process() -> None:
    operations = [
        operation(
            unit_id="U01",
            unit_code="U01",
            seq_no=1,
            process_code="TAPING",
            state="COMPLETED",
        ),
        operation(
            unit_id="U02",
            unit_code="U02",
            seq_no=1,
            process_code="TAPING",
            state="COMPLETED",
        ),
        operation(
            unit_id="U01",
            unit_code="U01",
            seq_no=3,
            process_code="GENERAL_ASSEMBLY",
            state="RUNNING",
        ),
        operation(
            unit_id="U02",
            unit_code="U02",
            seq_no=3,
            process_code="GENERAL_ASSEMBLY",
            state="WAITING",
        ),
    ]

    summary = build_lot_progress(operations, lot_id="LOT-101")

    taping = summary.processes[0]
    assembly = summary.processes[1]
    assert (taping.completed, taping.total, taping.fraction) == (2, 2, 1.0)
    assert (assembly.completed, assembly.total, assembly.running, assembly.waiting) == (
        0,
        2,
        1,
        1,
    )
    assert summary.current_process_code == "GENERAL_ASSEMBLY"


def test_build_lot_progress_ignores_other_lots() -> None:
    operations = [
        operation(
            lot_id="LOT-102",
            unit_id="LOT-102-U01",
            unit_code="U01",
            seq_no=1,
            process_code="TAPING",
            state="COMPLETED",
        )
    ]

    summary = build_lot_progress(operations, lot_id="LOT-101")

    assert all(process.total == 0 for process in summary.processes)
    assert summary.current_process_code is None


def test_build_process_unit_rows_groups_units_by_process_and_state() -> None:
    operations = [
        operation(
            unit_id="U01",
            unit_code="U01",
            seq_no=1,
            process_code="TAPING",
            state="COMPLETED",
        ),
        operation(
            unit_id="U02",
            unit_code="U02",
            seq_no=1,
            process_code="TAPING",
            state="WAITING",
        ),
        operation(
            unit_id="U03",
            unit_code="U03",
            seq_no=1,
            process_code="TAPING",
            state="HOLD",
        ),
        operation(
            unit_id="U01",
            unit_code="U01",
            seq_no=3,
            process_code="GENERAL_ASSEMBLY",
            state="RUNNING",
        ),
    ]

    rows = build_process_unit_rows(operations, lot_id="LOT-101")

    assert rows[0] == {
        "process_code": "TAPING",
        "completed": 1,
        "total": 3,
        "completed_units": ("U01",),
        "running_units": (),
        "hold_units": ("U03",),
        "waiting_units": ("U02",),
    }
    assert rows[1]["process_code"] == "GENERAL_ASSEMBLY"
    assert rows[1]["running_units"] == ("U01",)


def test_build_process_status_rows_keeps_forecast_at_process_resolution() -> None:
    operations = [
        operation(
            unit_id="U01",
            unit_code="U001",
            seq_no=1,
            process_code="TAPING",
            state="COMPLETED",
        ),
        operation(
            unit_id="U02",
            unit_code="U002",
            seq_no=1,
            process_code="TAPING",
            state="COMPLETED",
        ),
        operation(
            unit_id="U01",
            unit_code="U001",
            seq_no=4,
            process_code="TUNING",
            state="COMPLETED",
        ),
        operation(
            unit_id="U02",
            unit_code="U002",
            seq_no=4,
            process_code="TUNING",
            state="RUNNING",
        ),
    ]
    forecasts = [
        {
            "lot_id": "LOT-101",
            "process_code": "TAPING",
            "forecast_end": "2026-10-05T09:20:00+09:00",
        },
        {
            "lot_id": "LOT-101",
            "process_code": "TUNING",
            "forecast_end": "2026-10-05T12:30:00+09:00",
        },
        {
            "lot_id": "LOT-102",
            "process_code": "TUNING",
            "forecast_end": "2026-10-05T15:00:00+09:00",
        },
    ]

    rows = build_process_status_rows(operations, forecasts, lot_id="LOT-101")

    assert rows[0]["process_code"] == "TAPING"
    assert rows[0]["process_complete"] is True
    assert rows[0]["forecast_end"] is None
    assert rows[1]["process_code"] == "TUNING"
    assert rows[1]["process_complete"] is False
    assert rows[1]["forecast_end"] == "2026-10-05T12:30:00+09:00"
    assert rows[1]["completed_units"] == ("U001",)
    assert rows[1]["running_units"] == ("U002",)


def test_build_unit_detail_rows_uses_earliest_unfinished_process() -> None:
    operations = [
        operation(
            unit_id="U01",
            unit_code="U01",
            seq_no=1,
            process_code="TAPING",
            state="COMPLETED",
        ),
        operation(
            unit_id="U01",
            unit_code="U01",
            seq_no=3,
            process_code="GENERAL_ASSEMBLY",
            state="RUNNING",
            active_minutes=7.5,
        ),
        operation(
            unit_id="U01",
            unit_code="U01",
            seq_no=4,
            process_code="TUNING",
            state="WAITING",
        ),
    ]

    rows = build_unit_detail_rows(operations, lot_id="LOT-101")

    assert rows == (
        {
            "unit_code": "U01",
            "process_code": "GENERAL_ASSEMBLY",
            "state": "RUNNING",
            "attempt_no": 1,
            "active_minutes": 7.5,
        },
    )


def test_build_unit_detail_rows_keeps_final_test_pending_result_visible() -> None:
    operations = [
        operation(
            unit_id="U01",
            unit_code="U01",
            seq_no=6,
            process_code="FINAL_TEST",
            state="COMPLETED",
            result=None,
        )
    ]

    rows = build_unit_detail_rows(operations, lot_id="LOT-101")

    assert rows[0]["process_code"] == "FINAL_TEST"
    assert rows[0]["state"] == "COMPLETED"


def test_minimum_gate_slack_returns_tightest_lot_gate() -> None:
    gates = [
        {"lot_id": "LOT-101", "slack_minutes": 150},
        {"lot_id": "LOT-101", "slack_minutes": 45.5},
        {"lot_id": "LOT-102", "slack_minutes": -10},
    ]

    assert minimum_gate_slack(gates, lot_id="LOT-101") == 45.5
    assert minimum_gate_slack(gates, lot_id="LOT-999") is None


def test_shipping_inspection_expected_finish_counts_start_day_and_skips_weekend() -> None:
    monday_start = datetime(2026, 10, 5, 15, 30, tzinfo=SEOUL)
    friday_start = datetime(2026, 10, 9, 10, 0, tzinfo=SEOUL)

    monday_finish = shipping_inspection_expected_finish(monday_start)
    friday_finish = shipping_inspection_expected_finish(friday_start)

    assert monday_finish == datetime(2026, 10, 7, 17, 0, tzinfo=SEOUL)
    assert friday_finish == datetime(2026, 10, 13, 17, 0, tzinfo=SEOUL)


def test_shipping_inspection_expected_finish_rejects_naive_datetime() -> None:
    with pytest.raises(ValueError, match="timezone-aware"):
        shipping_inspection_expected_finish(datetime(2026, 10, 5, 15, 30))


def test_format_duration_minutes_is_human_readable() -> None:
    assert format_duration_minutes(172) == "2시간 52분"
    assert format_duration_minutes(1170) == "19시간 30분"
    assert format_duration_minutes(-30) == "-30분"
    assert format_duration_minutes(None) == "—"
