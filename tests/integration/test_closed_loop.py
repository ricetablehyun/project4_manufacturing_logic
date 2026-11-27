"""Closed loop: an approved plan must change what the shop floor executes.

World: F02 (2 LOTs x 4 Units). The baseline plan serves LOT-102 first although
LOT-101 has the earlier shipping-inspection Gate (10/05 15:30 vs 10/06 11:00),
so the system reports URGENT at the first review.
"""

from datetime import datetime
from pathlib import Path

import pytest

from production_control.sim.harness import build_harness
from production_control.sim.manager import ApprovalPolicy
from production_control.sim.runner import RunResult
from production_control.sim.truth import TruthModel
from production_control.sim.worlds import F02_START, build_f02_world

LATE_FIRST = ("LOT-102", "LOT-101")


def _run(
    tmp_path: Path,
    policy: ApprovalPolicy,
    *,
    truth: TruthModel | None = None,
    baseline: tuple[str, ...] = LATE_FIRST,
    resend_every: int = 0,
) -> RunResult:
    database_path = build_f02_world(tmp_path / f"{policy.value}.db", baseline_lot_order=baseline)
    harness = build_harness(
        database_path,
        truth=truth or TruthModel(),
        start_time=F02_START,
        run_tag=policy.value,
        resend_every=resend_every,
    )
    return harness.run(policy)


def _completion(result: RunResult, lot_id: str) -> datetime:
    return max(
        record.finished_at
        for record in result.plant.records
        if record.lot_id == lot_id
        and record.process_code == "FINAL_TEST"
        and record.result == "PASS"
    )


def _tuning_lot_sequence(result: RunResult) -> list[str]:
    records = sorted(
        (record for record in result.plant.records if record.process_code == "TUNING"),
        key=lambda record: record.started_at,
    )
    return [record.lot_id for record in records]


def test_approval_changes_the_executed_order(tmp_path: Path) -> None:
    keep = _run(tmp_path, ApprovalPolicy.KEEP)
    edd = _run(tmp_path, ApprovalPolicy.EDD)

    assert keep.violations == [] and edd.violations == []

    # KEEP: the system flags URGENT but nobody approves, so v1 runs to the end.
    assert keep.approvals == []
    assert keep.final_plan_version == 1
    assert _tuning_lot_sequence(keep) == ["LOT-102"] * 4 + ["LOT-101"] * 4

    # EDD: the manager approves at the first review; every later start carries
    # plan v2 and the tuning station switches to LOT-101 first.
    assert [(item.at, item.candidate_id) for item in edd.approvals] == [(F02_START, "EDD")]
    assert edd.final_plan_version == 2
    assert {record.plan_version for record in edd.plant.records} == {2}
    assert _tuning_lot_sequence(edd) == ["LOT-101"] * 4 + ["LOT-102"] * 4

    # The executed change is what moves LOT-101 ahead of its Gate.
    assert _completion(edd, "LOT-101") < _completion(keep, "LOT-101")


@pytest.mark.parametrize("baseline", [LATE_FIRST, ("LOT-101", "LOT-102")])
def test_deterministic_plant_realises_the_plan_forecast(
    tmp_path: Path,
    baseline: tuple[str, ...],
) -> None:
    """With true times equal to standard times, execution must equal the Forecast."""

    database_path = build_f02_world(tmp_path / "world.db", baseline_lot_order=baseline)
    harness = build_harness(
        database_path,
        truth=TruthModel(),
        start_time=F02_START,
        run_tag="DETERMINISTIC",
    )
    forecast = harness.terminal.forecast(F02_START)
    predicted = {
        lot["lot_id"]: datetime.fromisoformat(lot["forecast_end"]) for lot in forecast["lots"]
    }

    result = harness.run(ApprovalPolicy.KEEP)

    assert result.violations == []
    assert {lot_id: _completion(result, lot_id) for lot_id in predicted} == predicted


def test_noisy_plant_with_rework_and_resent_events_completes(tmp_path: Path) -> None:
    truth = TruthModel(
        seed=7,
        duration_sigma=0.35,
        final_test_fail_probability=0.25,
        estimate_sigma=0.2,
    )
    result = _run(tmp_path, ApprovalPolicy.RECOMMENDED, truth=truth, resend_every=3)

    assert result.violations == []
    failures = [record for record in result.plant.records if record.result == "FAIL"]
    assert failures, "seed 7 should produce at least one FINAL_TEST failure"
    # Every failed Unit was reworked and finally passed.
    for failure in failures:
        assert any(
            record.unit_id == failure.unit_id
            and record.process_code == "FINAL_TEST"
            and record.result == "PASS"
            and record.attempt_no > failure.attempt_no
            for record in result.plant.records
        )
    assert result.estimates, "Pace overruns should have asked the worker for estimates"
    assert result.calls.duplicate_events > 0
    assert all(_completion(result, lot_id) for lot_id in ("LOT-101", "LOT-102"))
