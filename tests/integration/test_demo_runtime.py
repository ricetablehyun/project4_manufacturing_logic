from datetime import datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

import pytest
from fastapi.testclient import TestClient

from production_control.demo.bootstrap import (
    DEMO_PLAN_ID,
    DEMO_SNAPSHOT_AT,
    DEMO_SNAPSHOT_RUNNING_OPERATION_ID,
    initialize_demo_database,
)
from production_control.demo.runtime import create_demo_app

SEOUL = ZoneInfo("Asia/Seoul")


def test_demo_bootstrap_serves_snapshot_through_real_api_boundary(tmp_path: Path) -> None:
    database_path = initialize_demo_database(tmp_path / "demo.db")
    client = TestClient(create_demo_app(database_path))

    lots = client.get("/lots")
    gates = client.get("/inspection-gates")
    forecast = client.get("/forecast", params={"as_of": DEMO_SNAPSHOT_AT.isoformat()})

    assert lots.status_code == 200
    assert [row["lot_id"] for row in lots.json()] == ["LOT-101", "LOT-102"]
    assert gates.status_code == 200
    assert len(gates.json()) == 2
    assert forecast.status_code == 200
    payload = forecast.json()
    assert payload["plan_id"] == DEMO_PLAN_ID
    assert payload["plan_version"] == 1
    assert payload["readiness"] == "READY"
    assert payload["waiting_operation_ids"] == []
    assert {row["lot_id"] for row in payload["lots"]} == {"LOT-101", "LOT-102"}


def test_demo_reset_starts_from_critical_late_stage_snapshot(tmp_path: Path) -> None:
    database_path = initialize_demo_database(tmp_path / "demo.db")
    client = TestClient(create_demo_app(database_path))

    response = client.get("/unit-operations")
    assert response.status_code == 200
    operations = response.json()

    lot_001_tuning = [
        row
        for row in operations
        if row["lot_id"] == "LOT-101" and row["process_code"] == "TUNING"
    ]
    lot_001_final_test = [
        row
        for row in operations
        if row["lot_id"] == "LOT-101" and row["process_code"] == "FINAL_TEST"
    ]
    lot_002_tuning = [
        row
        for row in operations
        if row["lot_id"] == "LOT-102" and row["process_code"] == "TUNING"
    ]

    assert sum(row["state"] == "COMPLETED" for row in lot_001_tuning) == 29
    assert sum(row["state"] == "COMPLETED" for row in lot_001_final_test) == 29
    running = [row for row in lot_001_tuning if row["state"] == "RUNNING"]
    assert len(running) == 1
    assert running[0]["operation_id"] == DEMO_SNAPSHOT_RUNNING_OPERATION_ID
    assert running[0]["unit_code"] == "U030"
    assert all(row["state"] == "WAITING" for row in lot_002_tuning)


def test_demo_hold_delays_only_critical_unit_and_recalculates_forecast(
    tmp_path: Path,
) -> None:
    database_path = initialize_demo_database(tmp_path / "demo.db")
    client = TestClient(create_demo_app(database_path))
    held_at = DEMO_SNAPSHOT_AT + timedelta(minutes=5)

    before = client.get("/forecast", params={"as_of": held_at.isoformat()})
    assert before.status_code == 200
    before_lot = next(row for row in before.json()["lots"] if row["lot_id"] == "LOT-101")

    held = client.post(
        "/work-events",
        json={
            "event_id": "DEMO-HOLD-U030",
            "unit_operation_id": DEMO_SNAPSHOT_RUNNING_OPERATION_ID,
            "event_type": "HOLD",
            "occurred_at": held_at.isoformat(),
            "station_code": None,
            "worker_code": "DEMO-WORKER",
            "reason": "TUNING_UNSTABLE",
            "expected_hold_minutes": 480,
        },
    )
    assert held.status_code == 201
    assert held.json()["state"] == "HOLD"

    forecast = client.get("/forecast", params={"as_of": held_at.isoformat()})
    assert forecast.status_code == 200
    payload = forecast.json()
    assert payload["readiness"] == "READY"
    assert payload["waiting_operation_ids"] == []
    after_lot = next(row for row in payload["lots"] if row["lot_id"] == "LOT-101")
    assert after_lot["forecast_end"] > before_lot["forecast_end"]


def test_demo_forecast_handles_running_event_before_normal_work_window(
    tmp_path: Path,
) -> None:
    database_path = initialize_demo_database(tmp_path / "demo.db")
    client = TestClient(create_demo_app(database_path))

    held_at = DEMO_SNAPSHOT_AT + timedelta(minutes=5)
    held = client.post(
        "/work-events",
        json={
            "event_id": "DEMO-PRE-SHIFT-PREP-HOLD",
            "unit_operation_id": DEMO_SNAPSHOT_RUNNING_OPERATION_ID,
            "event_type": "HOLD",
            "occurred_at": held_at.isoformat(),
            "station_code": None,
            "worker_code": None,
            "reason": "TUNING_UNSTABLE",
            "expected_hold_minutes": 60,
        },
    )
    assert held.status_code == 201

    started_at = datetime(2026, 10, 23, 8, 39, tzinfo=SEOUL)
    as_of = datetime(2026, 10, 23, 8, 40, tzinfo=SEOUL)
    started = client.post(
        "/work-events",
        json={
            "event_id": "DEMO-PRE-SHIFT-START",
            "unit_operation_id": "OP::LOT-102-U01::STEP-04-TUNING",
            "event_type": "START",
            "occurred_at": started_at.isoformat(),
            "station_code": None,
            "worker_code": None,
            "reason": None,
        },
    )
    assert started.status_code == 201

    forecast = client.get("/forecast", params={"as_of": as_of.isoformat()})
    assert forecast.status_code == 200
    assert forecast.json()["readiness"] == "READY"


def test_demo_wait_list_exposes_only_worker_actionable_running_operation(
    tmp_path: Path,
) -> None:
    database_path = initialize_demo_database(tmp_path / "demo.db")
    client = TestClient(create_demo_app(database_path))
    far_future = DEMO_SNAPSHOT_AT + timedelta(days=5)

    forecast = client.get("/forecast", params={"as_of": far_future.isoformat()})

    assert forecast.status_code == 200
    payload = forecast.json()
    assert payload["readiness"] == "WAIT"
    assert payload["waiting_operation_ids"] == [DEMO_SNAPSHOT_RUNNING_OPERATION_ID]


def test_demo_uses_shop_floor_codes_and_realistic_lot_scale(tmp_path: Path) -> None:
    database_path = initialize_demo_database(tmp_path / "demo.db")
    client = TestClient(create_demo_app(database_path))

    lots = client.get("/lots")
    gates = client.get("/inspection-gates")
    operations = client.get("/unit-operations")

    assert lots.status_code == 200
    assert gates.status_code == 200
    assert operations.status_code == 200

    lots_by_id = {row["lot_id"]: row for row in lots.json()}
    assert lots_by_id["LOT-101"]["lot_code"] == "LOT-001"
    assert lots_by_id["LOT-102"]["lot_code"] == "LOT-002"
    assert lots_by_id["LOT-101"]["quantity"] == 30
    assert lots_by_id["LOT-102"]["quantity"] == 30

    unit_codes = sorted({row["unit_code"] for row in operations.json()})
    assert len(unit_codes) == 60
    assert unit_codes[0] == "U001"
    assert unit_codes[29] == "U030"
    assert unit_codes[30] == "U031"
    assert unit_codes[-1] == "U060"

    gates_by_lot = {row["lot_id"]: row for row in gates.json()}
    assert gates_by_lot["LOT-101"]["planned_at"].startswith("2026-10-23T09:00")
    assert gates_by_lot["LOT-102"]["planned_at"].startswith("2026-11-06T09:00")


def test_demo_current_plan_is_lot_process_scale_not_unit_schedule(tmp_path: Path) -> None:
    database_path = initialize_demo_database(tmp_path / "demo.db")
    client = TestClient(create_demo_app(database_path))

    response = client.get("/schedule-plan/current")

    assert response.status_code == 200
    payload = response.json()
    assert payload["plan_id"] == DEMO_PLAN_ID
    assert payload["version"] == 1
    assert len(payload["tasks"]) == 10
    assert {task["target_qty"] for task in payload["tasks"]} == {30}

    tasks = {(task["lot_id"], task["process_code"]): task for task in payload["tasks"]}
    assert tasks[("LOT-101", "TAPING")]["target_start"].startswith("2026-09-28T09:00")
    assert tasks[("LOT-101", "TUNING")]["target_end"].startswith("2026-10-19T17:00")
    assert tasks[("LOT-102", "TUNING")]["target_start"].startswith("2026-10-20T09:00")


def test_demo_bootstrap_requires_explicit_reset_to_replace_existing_db(
    tmp_path: Path,
) -> None:
    database_path = tmp_path / "demo.db"
    initialize_demo_database(database_path)

    with pytest.raises(FileExistsError, match="use --reset"):
        initialize_demo_database(database_path)


def test_demo_reset_restores_deterministic_initial_state(tmp_path: Path) -> None:
    database_path = initialize_demo_database(tmp_path / "demo.db")
    client = TestClient(create_demo_app(database_path))

    changed = client.patch("/lots/LOT-101", json={"status": "PAUSED"})
    assert changed.status_code == 200

    initialize_demo_database(database_path, reset=True)
    reset_client = TestClient(create_demo_app(database_path))
    operations = reset_client.get("/unit-operations")

    assert operations.status_code == 200
    running = next(
        row
        for row in operations.json()
        if row["operation_id"] == DEMO_SNAPSHOT_RUNNING_OPERATION_ID
    )
    assert running["state"] == "RUNNING"
    assert running["unit_code"] == "U030"


def test_demo_runtime_rejects_missing_uninitialized_database(tmp_path: Path) -> None:
    missing_path = tmp_path / "missing.db"

    with pytest.raises(FileNotFoundError, match="not initialized"):
        create_demo_app(missing_path)
