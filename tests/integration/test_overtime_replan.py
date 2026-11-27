"""D078 weekday overtime: offered, approved, forecast and executed consistently.

World: F02 (2 LOTs x 4 Units) starting at 13:00 with both shipping-inspection
Gates early on the next morning (LOT-101 09:00, LOT-102 09:30). On the regular
calendar even the best rule leaves one LOT late; two hours of overtime on the
first day remove the delay.
"""

from dataclasses import replace
from datetime import datetime, time
from pathlib import Path

import pytest

from production_control.sim.harness import DEFAULT_FORECAST_CONFIG, build_harness
from production_control.sim.manager import ApprovalPolicy
from production_control.sim.runner import RunResult
from production_control.sim.truth import TruthModel
from production_control.sim.worlds import SEOUL, build_f02_world

START = datetime(2026, 10, 5, 13, 0, tzinfo=SEOUL)
GATES = {
    "LOT-101": datetime(2026, 10, 6, 9, 0, tzinfo=SEOUL),
    "LOT-102": datetime(2026, 10, 6, 9, 30, tzinfo=SEOUL),
}
REGULAR_CLOSE = datetime(2026, 10, 5, 17, 0, tzinfo=SEOUL)
OVERTIME_CLOSE = datetime(2026, 10, 5, 19, 0, tzinfo=SEOUL)
WITH_OVERTIME = replace(DEFAULT_FORECAST_CONFIG, overtime_end=time(19, 0))


def _harness(tmp_path: Path, name: str, *, overtime: bool):
    database_path = build_f02_world(
        tmp_path / f"{name}.db",
        baseline_lot_order=("LOT-102", "LOT-101"),
        gate_planned_at=GATES,
    )
    return build_harness(
        database_path,
        truth=TruthModel(),
        start_time=START,
        run_tag=name,
        forecast_config=WITH_OVERTIME if overtime else DEFAULT_FORECAST_CONFIG,
    )


def _completion(result: RunResult, lot_id: str) -> datetime:
    return max(
        record.finished_at
        for record in result.plant.records
        if record.lot_id == lot_id
        and record.process_code == "FINAL_TEST"
        and record.result == "PASS"
    )


def test_overtime_variant_is_offered_only_when_enabled(tmp_path: Path) -> None:
    regular = _harness(tmp_path, "regular", overtime=False).terminal.replan_candidates(START)
    assert all("+OT" not in row["candidate_id"] for row in regular["candidates"])

    snapshot = _harness(tmp_path, "overtime", overtime=True).terminal.replan_candidates(START)
    rows = {row["candidate_id"]: row for row in snapshot["candidates"]}

    assert rows["EDD"]["kpi"]["late_lot_count"] == 1
    assert rows["EDD"]["kpi"]["total_tardiness_minutes"] == pytest.approx(90.0)
    assert rows["EDD+OT"]["kpi"]["late_lot_count"] == 0
    assert rows["EDD+OT"]["kpi"]["total_tardiness_minutes"] == 0.0
    assert rows["EDD+OT"]["kpi"]["overtime_minutes"] == pytest.approx(120.0)
    assert rows["EDD+OT"]["overtime_days"] == ["2026-10-05"]
    assert rows["EDD+OT"]["lot_priority_order"] == rows["EDD"]["lot_priority_order"]
    assert snapshot["recommended_candidate_id"] == "EDD+OT"


def test_approved_overtime_is_what_the_forecast_then_uses(tmp_path: Path) -> None:
    harness = _harness(tmp_path, "approve", overtime=True)
    terminal = harness.terminal
    snapshot = terminal.replan_candidates(START)
    selected = next(row for row in snapshot["candidates"] if row["candidate_id"] == "EDD+OT")

    terminal.approve(
        parent_plan_id=snapshot["parent_plan_id"], candidate_id="EDD+OT", as_of=START
    )

    calendar = terminal.work_calendar()
    assert [
        (datetime.fromisoformat(item["start_at"]), datetime.fromisoformat(item["end_at"]))
        for item in calendar["overtime"]
    ] == [(REGULAR_CLOSE, OVERTIME_CLOSE)]
    forecast = terminal.forecast(START)
    late = [lot for lot in forecast["lots"] if lot["risk_level"] == "URGENT"]
    assert late == []
    assert terminal.current_plan()["version"] == 2
    assert selected["kpi"]["late_lot_count"] == 0

    # With true times equal to standard times the plant realises that Forecast,
    # working through the approved overtime window.
    predicted = {
        lot["lot_id"]: datetime.fromisoformat(lot["forecast_end"]) for lot in forecast["lots"]
    }
    result = harness.run(ApprovalPolicy.KEEP)
    assert result.violations == []
    assert {lot_id: _completion(result, lot_id) for lot_id in predicted} == predicted
    assert max(predicted.values()) > REGULAR_CLOSE


def test_closed_loop_works_the_approved_overtime(tmp_path: Path) -> None:
    regular = _harness(tmp_path, "loop-regular", overtime=False).run(ApprovalPolicy.EDD)
    overtime = _harness(tmp_path, "loop-overtime", overtime=True).run(ApprovalPolicy.EDD)

    assert regular.violations == [] and overtime.violations == []
    assert [item.candidate_id for item in regular.approvals] == ["EDD"]
    assert [item.candidate_id for item in overtime.approvals] == ["EDD+OT"]

    # Work physically ran between 17:00 and 19:00 only where overtime was approved.
    def worked_in_window(result: RunResult) -> list[str]:
        return [
            record.unit_operation_id
            for record in result.plant.records
            if REGULAR_CLOSE <= record.started_at < OVERTIME_CLOSE
            or REGULAR_CLOSE < record.finished_at <= OVERTIME_CLOSE
        ]

    assert worked_in_window(overtime)
    assert worked_in_window(regular) == []

    # Overtime is what brings both LOTs in before their Gates.
    assert any(_completion(regular, lot) > gate for lot, gate in GATES.items())
    assert all(_completion(overtime, lot) <= gate for lot, gate in GATES.items())
