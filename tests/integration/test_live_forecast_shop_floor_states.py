"""Shop-floor states the closed loop reaches that the Forecast must handle.

Each case is a state the virtual plant produced in a real closed-loop run and
that previously left the Live Forecast unable to schedule (deadlock or a WAIT
nobody could resolve). They are driven through the public API only.
"""

from datetime import datetime, timedelta
from pathlib import Path

from production_control.sim.harness import build_harness
from production_control.sim.terminal import ShopFloorTerminal
from production_control.sim.truth import TruthModel
from production_control.sim.worlds import F02_START, build_f02_world

STANDARD = {
    "TAPING": 10,
    "GENERAL_ASSEMBLY": 10,
    "TUNING": 25,
    "FINISH_ASSEMBLY": 10,
    "FINAL_TEST": 30,
}


def _terminal(tmp_path: Path) -> ShopFloorTerminal:
    database_path = build_f02_world(tmp_path / "world.db")
    harness = build_harness(
        database_path, truth=TruthModel(), start_time=F02_START, run_tag="STATE"
    )
    return harness.terminal


def _run_operation(
    terminal: ShopFloorTerminal,
    operation_id: str,
    process_code: str,
    started_at: datetime,
    *,
    result: str = "COMPLETE",
    attempt_no: int = 1,
) -> datetime:
    terminal.report(
        unit_operation_id=operation_id,
        attempt_no=attempt_no,
        event_type="START",
        occurred_at=started_at,
    )
    finished_at = started_at + timedelta(minutes=STANDARD[process_code])
    terminal.report(
        unit_operation_id=operation_id,
        attempt_no=attempt_no,
        event_type=result,
        occurred_at=finished_at,
        reason="TEST_FAIL" if result == "FAIL" else None,
    )
    return finished_at


def _operations(terminal: ShopFloorTerminal, unit_id: str) -> list[dict]:
    rows = [row for row in terminal.unit_operations() if row["unit_id"] == unit_id]
    return sorted(rows, key=lambda row: row["seq_no"])


def test_work_orders_follow_the_plan_and_are_not_reissued_after_start(tmp_path: Path) -> None:
    terminal = _terminal(tmp_path)

    first = terminal.work_orders(F02_START)
    assert first["readiness"] == "READY"
    assert first["plan_version"] == 1
    issued = [order["unit_operation_id"] for order in first["orders"]]
    assert issued == ["OP::LOT-101-U01::STEP-01-TAPING", "OP::LOT-101-U02::STEP-01-TAPING"]

    for operation_id in issued:
        terminal.report(
            unit_operation_id=operation_id,
            attempt_no=1,
            event_type="START",
            occurred_at=F02_START,
        )

    again = terminal.work_orders(F02_START)
    assert again["orders"] == []
    assert datetime.fromisoformat(again["next_start_at"]) == F02_START + timedelta(minutes=10)


def test_release_buffer_counts_upstream_units_finished_before_the_snapshot(
    tmp_path: Path,
) -> None:
    """FINISH_ASSEMBLY needs K=2 finished TUNING Units. After three Units finished
    TUNING only one remains upstream; the Forecast must not wait for two more."""

    terminal = _terminal(tmp_path)
    moment = F02_START
    for unit in ("U01", "U02", "U03"):
        for operation in _operations(terminal, f"LOT-101-{unit}")[:3]:
            moment = _run_operation(
                terminal, operation["operation_id"], operation["process_code"], moment
            )

    forecast = terminal.forecast(moment)

    assert forecast["readiness"] == "READY"
    orders = terminal.work_orders(moment)["orders"]
    assert any(
        order["lot_id"] == "LOT-101" and order["process_code"] == "FINISH_ASSEMBLY"
        for order in orders
    )


def test_forecast_after_final_test_failure_includes_rework_and_retest(tmp_path: Path) -> None:
    terminal = _terminal(tmp_path)
    moment = F02_START
    operations = _operations(terminal, "LOT-101-U01")
    for operation in operations[:-1]:
        moment = _run_operation(
            terminal, operation["operation_id"], operation["process_code"], moment
        )
    moment = _run_operation(
        terminal, operations[-1]["operation_id"], "FINAL_TEST", moment, result="FAIL"
    )

    # The retest attempt does not exist yet; the Forecast projects it.
    forecast = terminal.forecast(moment)
    assert forecast["readiness"] == "READY"
    lot = next(item for item in forecast["lots"] if item["lot_id"] == "LOT-101")
    assert datetime.fromisoformat(lot["forecast_end"]) > moment

    tuning = next(
        row for row in _operations(terminal, "LOT-101-U01") if row["process_code"] == "TUNING"
    )
    assert (tuning["state"], tuning["attempt_no"]) == ("WAITING", 2)
    terminal.report(
        unit_operation_id=tuning["operation_id"],
        attempt_no=2,
        event_type="START",
        occurred_at=moment,
    )

    # A RUNNING rework attempt is scheduled for its remaining Pace time.
    running = terminal.forecast(moment + timedelta(minutes=5))
    assert running["readiness"] == "READY"
