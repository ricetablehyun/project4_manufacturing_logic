from datetime import datetime
from zoneinfo import ZoneInfo

import pytest

from production_control.ui import charts
from production_control.ui.gantt_model import (
    CANDIDATE_LAYER,
    FORECAST_LAYER,
    forecast_bars,
    gate_markers,
    plan_bars,
    plant_time,
    records,
    step_process_map,
)

pytest.importorskip("altair")

SEOUL = ZoneInfo("Asia/Seoul")
LOTS = {"LOT-101": "LOT-001"}


def test_plant_time_is_seoul_wall_clock_regardless_of_offset() -> None:
    assert plant_time("2026-10-22T04:00:00Z") == "2026-10-22T13:00"
    assert plant_time(datetime(2026, 10, 22, 13, 0, tzinfo=SEOUL)) == "2026-10-22T13:00"
    assert plant_time("2026-10-22T13:00:00") is None  # naive: refuse to guess


def test_candidate_tasks_take_their_process_from_the_unit_operations() -> None:
    operations = [{"lot_id": "LOT-101", "routing_step_id": "S4", "process_code": "TUNING"}]
    tasks = [
        {
            "lot_id": "LOT-101",
            "routing_step_id": "S4",
            "target_start": "2026-10-22T13:00:00+09:00",
            "target_end": "2026-10-22T15:00:00+09:00",
        },
        {  # unknown step: left out rather than mislabelled
            "lot_id": "LOT-101",
            "routing_step_id": "S9",
            "target_start": "2026-10-22T13:00:00+09:00",
            "target_end": "2026-10-22T15:00:00+09:00",
        },
    ]

    bars = plan_bars(
        tasks, lot_labels=LOTS, layer=CANDIDATE_LAYER, step_process=step_process_map(operations)
    )

    assert [(bar.lot_label, bar.process_code, bar.layer) for bar in bars] == [
        ("LOT-001", "TUNING", CANDIDATE_LAYER)
    ]


def test_forecast_bars_skip_empty_windows_and_completed_gates_are_not_marked() -> None:
    bars = forecast_bars(
        [
            {
                "lot_id": "LOT-101",
                "process_code": "FINAL_TEST",
                "forecast_start": "2026-10-22T13:00:00+09:00",
                "forecast_end": "2026-10-22T14:00:00+09:00",
            },
            {
                "lot_id": "LOT-101",
                "process_code": "TUNING",
                "forecast_start": "2026-10-22T13:00:00+09:00",
                "forecast_end": "2026-10-22T13:00:00+09:00",
            },
        ],
        lot_labels=LOTS,
    )
    markers = gate_markers(
        [
            {"lot_id": "LOT-101", "gate_type": "SHIPPING_INSPECTION",
             "planned_at": "2026-10-23T09:00:00+09:00", "completed_at": None},
            {"lot_id": "LOT-101", "gate_type": "VISUAL_INSPECTION",
             "planned_at": "2026-10-21T09:00:00+09:00",
             "completed_at": "2026-10-21T10:00:00+09:00"},
        ],
        lot_labels=LOTS,
    )  # fmt: skip

    assert [(bar.process_code, bar.layer) for bar in bars] == [("FINAL_TEST", FORECAST_LAYER)]
    assert [(marker.label, marker.at) for marker in markers] == [
        ("출하검사 예정", "2026-10-23T09:00")
    ]
    spec = charts.gantt_chart(
        records(bars), markers=records(markers), now="2026-10-22T13:00"
    ).to_dict()
    assert spec["layer"][0]["encoding"]["x"]["scale"]["domain"][0] == "2026-10-22T13:00"


def _summary_row(condition: str, policy: str, mean: float, half: float) -> dict[str, str]:
    row = {key: "0" for key in (
        "late_gate_lots_mean", "due_tardiness_minutes_mean", "due_tardiness_minutes_ci95",
        "overtime_minutes_mean", "approvals_mean", "gate_delay_minutes_vs_keep_mean",
        "gate_delay_minutes_vs_keep_ci95",
    )}  # fmt: skip
    row.update(
        condition=condition,
        policy=policy,
        n="30",
        gate_delay_minutes_mean=str(mean),
        gate_delay_minutes_ci95=str(half),
    )
    return row


def test_summary_records_split_overtime_and_clip_ci_at_zero() -> None:
    rows = charts.summary_records(
        [_summary_row("NORMAL", "EDD+OT", 2.0, 5.0), _summary_row("SLOW", "KEEP", 100.0, 10.0)]
    )

    assert rows[0]["rule"] == "EDD" and rows[0]["overtime"] is True
    assert rows[0]["gate_delay_low"] == 0.0 and rows[0]["gate_delay_high"] == 7.0
    assert rows[1]["condition_label"] == "작업시간 +20%" and rows[1]["overtime"] is False
    for chart in (charts.gate_delay_chart(rows), charts.overtime_tradeoff_chart(rows)):
        assert chart.to_dict()["facet"]


def test_candidate_label_names_the_overtime_window() -> None:
    from production_control.ui.overview import candidate_label

    assert candidate_label({"rule": "EDD"}).startswith("EDD")
    label = candidate_label(
        {"rule": "EDD", "overtime_days": ["2026-10-22"], "overtime_end": "19:00:00"}
    )
    assert label.endswith("+ 추가근무(~19:00, 10/22)")


def test_demo_clock_is_fixed_only_when_configured(monkeypatch) -> None:
    from production_control.ui.overview import demo_now

    monkeypatch.setenv("PRODUCTION_CONTROL_DEMO_TIME", "2026-10-22T13:17:00+09:00")
    assert demo_now() == datetime(2026, 10, 22, 13, 17, tzinfo=SEOUL)

    monkeypatch.setenv("PRODUCTION_CONTROL_DEMO_TIME", "2026-10-22T13:17:00")
    with pytest.raises(ValueError):
        demo_now()

    monkeypatch.delenv("PRODUCTION_CONTROL_DEMO_TIME")
    assert demo_now().year >= 2026
