from dataclasses import dataclass, field, replace
from datetime import date, datetime, time
from zoneinfo import ZoneInfo

import pytest

from production_control.core.calendar_engine import WorkCalendar
from production_control.sim.experiment import (
    RunRow,
    lot_outcomes,
    mean_ci,
    plan_runs,
    summarise,
    worked_overtime_minutes,
)
from production_control.sim.manager import ApprovalPolicy
from production_control.sim.plant import ExecutionRecord
from production_control.sim.truth import TruthModel

SEOUL = ZoneInfo("Asia/Seoul")


def at(day: int, hour: int, minute: int = 0) -> datetime:
    return datetime(2026, 10, day, hour, minute, tzinfo=SEOUL)


def record(lot_id: str, start: datetime, end: datetime, process: str = "FINAL_TEST", result="PASS"):
    return ExecutionRecord(
        unit_operation_id=f"OP::{lot_id}::{start.isoformat()}",
        lot_id=lot_id,
        unit_id=f"{lot_id}-U01",
        unit_code="U01",
        process_code=process,
        attempt_no=1,
        started_at=start,
        finished_at=end,
        true_minutes=(end - start).total_seconds() / 60,
        result=result,
        plan_version=1,
    )


@dataclass
class FakePlant:
    records: list = field(default_factory=list)


@dataclass
class FakeResult:
    plant: FakePlant


def test_plan_runs_pairs_seeds_and_skips_keep_with_overtime() -> None:
    specs = plan_runs(reps=2, conditions=["NORMAL"])

    assert len(specs) == 2 * (1 + 4 * 2)
    assert not any(spec.policy == "KEEP" and spec.overtime for spec in specs)
    assert {spec.seed for spec in specs} == {1, 2}


def test_gate_delay_and_final_due_tardiness_are_separate_metrics() -> None:
    regular = WorkCalendar()
    result = FakeResult(
        FakePlant(
            [
                record("LOT-A", at(22, 9), at(22, 12)),  # gate 10/22 10:00 -> 120 late
                record("LOT-A", at(22, 13), at(22, 14), result="FAIL"),
                record("LOT-B", at(22, 9), at(22, 10)),  # on time
            ]
        )
    )

    outcomes = lot_outcomes(
        result,
        gates={"LOT-A": at(22, 10), "LOT-B": at(23, 9)},
        dues={"LOT-A": at(27, 17), "LOT-B": at(23, 17)},
        regular=regular,
        started_at=at(22, 9),
        inspection_lead_minutes=3 * 8 * 60,
    )
    by_lot = {item.lot_id: item for item in outcomes}

    assert by_lot["LOT-A"].gate_delay_minutes == 120
    # Shipped 3 working days after 10/22 12:00 = 10/27 12:00, before its due.
    assert by_lot["LOT-A"].shipped_at == at(27, 12)
    assert by_lot["LOT-A"].due_tardiness_minutes == 0
    assert by_lot["LOT-B"].gate_delay_minutes == 0
    # LOT-B ships 10/27 10:00 but was due 10/23 17:00.
    assert by_lot["LOT-B"].due_tardiness_minutes == pytest.approx(
        (at(27, 10) - at(23, 17)).total_seconds() / 60
    )
    assert by_lot["LOT-A"].completion_working_hours == 3


def test_worked_overtime_counts_only_work_after_the_regular_close() -> None:
    calendar = WorkCalendar().with_overtime([date(2026, 10, 22)], time(19, 0))
    result = FakeResult(
        FakePlant(
            [
                record("LOT-A", at(22, 16, 30), at(22, 17, 45), process="TUNING", result=None),
                record("LOT-A", at(22, 17, 50), at(22, 18, 20), process="TUNING", result=None),
                record("LOT-A", at(23, 9), at(23, 16), process="TUNING", result=None),
            ]
        )
    )

    assert worked_overtime_minutes(result, calendar) == 80


def _row(policy: str, seed: int, delay: float, overtime: bool = False) -> RunRow:
    return RunRow(
        condition="NORMAL", policy=policy, overtime=overtime, seed=seed,
        late_gate_lots=int(delay > 0), gate_delay_minutes=delay, late_due_lots=0,
        due_tardiness_minutes=0.0, on_time_rate=1.0, mean_completion_hours=10.0,
        overtime_minutes=0.0, approvals=0, approved_candidates="", final_plan_version=1,
        replan_reviews=0, worker_estimates=0, final_test_failures=0, steps=1,
        violations=0, wall_seconds=1.0, lot_detail="[]",
    )  # fmt: skip


def test_summary_reports_paired_difference_against_keep() -> None:
    rows = [
        _row("KEEP", 1, 200), _row("KEEP", 2, 100),
        _row("EDD", 1, 50), _row("EDD", 2, 0),
    ]  # fmt: skip

    summary = {entry["policy"]: entry for entry in summarise(rows)}

    assert summary["EDD"]["gate_delay_minutes_mean"] == 25
    assert summary["EDD"]["gate_delay_minutes_vs_keep_mean"] == -125
    assert summary["KEEP"]["gate_delay_minutes_vs_keep_mean"] == 0


def test_mean_ci_uses_student_t() -> None:
    value, half = mean_ci([1.0, 2.0, 3.0])
    assert value == 2.0
    assert half == pytest.approx(4.303 * 1.0 / 3**0.5)


def test_condition_disturbances_are_keyed_and_slow_down_on_average() -> None:
    slow = TruthModel(seed=3, duration_multiplier=1.2)
    held = TruthModel(seed=3, hold_probability=0.5, hold_minutes=240)
    ids = [f"OP-{index}" for index in range(200)]

    assert all(
        slow.true_minutes(unit_operation_id=op, attempt_no=1, standard_minutes=25) == 30
        for op in ids
    )
    held_minutes = [
        held.true_minutes(unit_operation_id=op, attempt_no=1, standard_minutes=25) for op in ids
    ]
    assert set(held_minutes) == {25.0, 265.0}
    assert held_minutes == [
        held.true_minutes(unit_operation_id=op, attempt_no=1, standard_minutes=25) for op in ids
    ]
    assert ApprovalPolicy.KEEP.value == "KEEP"


def test_interrupted_experiment_resumes_without_repeating_runs(tmp_path, monkeypatch) -> None:
    import production_control.sim.experiment as experiment

    executed: list = []

    def fake_execute(spec):
        executed.append(spec)
        return replace(_row(spec.policy, spec.seed, 10.0), overtime=spec.overtime)

    monkeypatch.setattr(experiment, "execute", fake_execute)
    specs = plan_runs(
        reps=1, conditions=["NORMAL"], policies=[ApprovalPolicy.KEEP, ApprovalPolicy.EDD]
    )

    experiment.run_experiment(specs[:2], out=tmp_path, workers=1, progress=False)
    rows = experiment.run_experiment(specs, out=tmp_path, workers=1, progress=False)

    assert executed == specs[:2] + specs[2:]
    assert [(row.policy, row.overtime) for row in rows] == [
        (spec.policy, spec.overtime) for spec in specs
    ]
    assert (tmp_path / "summary.csv").exists()


def test_a_failed_run_is_recorded_and_the_rest_still_run(tmp_path, monkeypatch) -> None:
    import json

    import production_control.sim.experiment as experiment

    def flaky_execute(spec):
        if spec.policy == "EDD" and not spec.overtime:
            raise RuntimeError("boom")
        return replace(_row(spec.policy, spec.seed, 10.0), overtime=spec.overtime)

    monkeypatch.setattr(experiment, "execute", flaky_execute)
    specs = plan_runs(
        reps=1, conditions=["NORMAL"], policies=[ApprovalPolicy.KEEP, ApprovalPolicy.EDD]
    )

    rows = experiment.run_experiment(specs, out=tmp_path, workers=1, progress=False)

    assert len(rows) == len(specs) - 1
    failures = json.loads((tmp_path / "failures.json").read_text())
    assert [(item["policy"], item["overtime"]) for item in failures] == [("EDD", False)]
    assert "boom" in failures[0]["error"]
