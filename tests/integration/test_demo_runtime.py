from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import pytest
from fastapi.testclient import TestClient

from production_control.demo.bootstrap import (
    DEMO_PLAN_ID,
    initialize_demo_database,
)
from production_control.demo.runtime import create_demo_app

SEOUL = ZoneInfo("Asia/Seoul")


def test_demo_bootstrap_serves_fixture_through_real_api_boundary(tmp_path: Path) -> None:
    database_path = initialize_demo_database(tmp_path / "demo.db")
    client = TestClient(create_demo_app(database_path))

    lots = client.get("/lots")
    gates = client.get("/inspection-gates")
    forecast = client.get(
        "/forecast",
        params={
            "as_of": datetime(2026, 10, 5, 9, 5, tzinfo=SEOUL).isoformat(),
        },
    )

    assert lots.status_code == 200
    assert [row["lot_id"] for row in lots.json()] == ["LOT-101", "LOT-102"]
    assert gates.status_code == 200
    assert len(gates.json()) == 2
    assert forecast.status_code == 200
    assert forecast.json()["plan_id"] == DEMO_PLAN_ID
    assert forecast.json()["plan_version"] == 1
    assert forecast.json()["readiness"] == "READY"
    assert {row["lot_id"] for row in forecast.json()["lots"]} == {
        "LOT-101",
        "LOT-102",
    }


def test_demo_forecast_handles_running_event_before_normal_work_window(
    tmp_path: Path,
) -> None:
    database_path = initialize_demo_database(tmp_path / "demo.db")
    client = TestClient(create_demo_app(database_path))
    started_at = datetime(2026, 9, 29, 8, 39, tzinfo=SEOUL)
    as_of = datetime(2026, 9, 29, 8, 40, tzinfo=SEOUL)

    started = client.post(
        "/work-events",
        json={
            "event_id": "DEMO-PRE-SHIFT-START",
            "unit_operation_id": "OP::LOT-101-U01::STEP-01-TAPING",
            "event_type": "START",
            "occurred_at": started_at.isoformat(),
            "station_code": None,
            "worker_code": None,
            "reason": None,
        },
    )
    assert started.status_code == 201

    forecast = client.get(
        "/forecast",
        params={"as_of": as_of.isoformat()},
    )

    assert forecast.status_code == 200
    payload = forecast.json()
    assert payload["as_of"] == as_of.isoformat()
    assert payload["readiness"] == "READY"
    assert payload["waiting_operation_ids"] == []


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
    assert lots_by_id["LOT-101"]["release_at"].startswith("2026-09-28T09:00")
    assert lots_by_id["LOT-102"]["release_at"].startswith("2026-10-05T09:00")
    assert lots_by_id["LOT-101"]["due_at"].startswith("2026-10-29T17:00")
    assert lots_by_id["LOT-102"]["due_at"].startswith("2026-11-12T17:00")

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

    tasks = {
        (task["lot_id"], task["process_code"]): task
        for task in payload["tasks"]
    }
    lot_001_taping = tasks[("LOT-101", "TAPING")]
    lot_001_tuning = tasks[("LOT-101", "TUNING")]
    lot_002_tuning = tasks[("LOT-102", "TUNING")]

    assert lot_001_taping["target_start"].startswith("2026-09-28T09:00")
    assert lot_001_taping["target_end"].startswith("2026-09-29T13:00")
    assert lot_001_tuning["target_end"].startswith("2026-10-19T17:00")
    assert lot_002_tuning["target_start"].startswith("2026-10-20T09:00")
    assert lot_002_tuning["target_end"].startswith("2026-11-02T17:00")


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
    assert changed.json()["status"] == "PAUSED"

    initialize_demo_database(database_path, reset=True)
    reset_client = TestClient(create_demo_app(database_path))
    lots = reset_client.get("/lots")

    assert lots.status_code == 200
    lot_101 = next(row for row in lots.json() if row["lot_id"] == "LOT-101")
    assert lot_101["status"] == "ACTIVE"
    assert lot_101["quantity"] == 30


def test_demo_runtime_rejects_missing_uninitialized_database(tmp_path: Path) -> None:
    missing_path = tmp_path / "missing.db"

    with pytest.raises(FileNotFoundError, match="not initialized"):
        create_demo_app(missing_path)
