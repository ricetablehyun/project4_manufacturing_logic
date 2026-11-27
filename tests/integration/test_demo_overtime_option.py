"""The demo runtime's opt-in overtime (D078) on the midterm delay smoke.

With ``overtime_end=19:00`` the same state that the midterm presentation showed
also offers "<RULE>+OT" candidates. The regular candidates keep their midterm
KPIs, and two hours of overtime on 10/22 cut the remaining 297-minute Gate delay
to 177 minutes. Without the option nothing changes (see
test_midterm_kpi_regression.py).
"""

from datetime import time
from pathlib import Path

from fastapi.testclient import TestClient

from production_control.demo.bootstrap import (
    DEMO_SNAPSHOT_RUNNING_OPERATION_ID,
    initialize_demo_database,
)
from production_control.demo.prepare_delay_smoke import prepare_delay_smoke
from production_control.demo.runtime import create_demo_app


def test_demo_overtime_option_adds_overtime_candidates(tmp_path: Path) -> None:
    database_path = initialize_demo_database(tmp_path / "demo.db")
    reference_time = prepare_delay_smoke(database_path)
    client = TestClient(create_demo_app(database_path, overtime_end=time(19, 0)))
    assert (
        client.patch(
            f"/unit-operations/{DEMO_SNAPSHOT_RUNNING_OPERATION_ID}/expected-remaining",
            json={"expected_remaining_minutes": 480},
        ).status_code
        == 200
    )

    response = client.post("/replan-candidates", params={"as_of": reference_time.isoformat()})
    assert response.status_code == 200
    payload = response.json()
    rows = {
        row["candidate_id"]: (
            row["kpi"]["late_lot_count"],
            row["kpi"]["total_tardiness_minutes"],
            row["kpi"]["overtime_minutes"],
            row["overtime_days"],
        )
        for row in payload["candidates"]
    }

    assert rows["FCFS"] == (2, 549.0, 0.0, [])
    assert rows["EDD"] == (1, 297.0, 0.0, [])
    assert rows["EDD+OT"] == (1, 177.0, 120.0, ["2026-10-22"])
    assert rows["FCFS+OT"] == (1, 177.0, 360.0, ["2026-10-22", "2026-10-23", "2026-10-26"])
    assert payload["recommended_candidate_id"] == "EDD+OT"


def test_approving_the_overtime_candidate_opens_the_window_and_updates_the_forecast(
    tmp_path: Path,
) -> None:
    """The demo's approval path: EDD+OT -> plan v2, 10/22 17-19 open, Gate -177."""

    database_path = initialize_demo_database(tmp_path / "demo.db")
    reference_time = prepare_delay_smoke(database_path)
    client = TestClient(create_demo_app(database_path, overtime_end=time(19, 0)))
    as_of = {"as_of": reference_time.isoformat()}
    client.patch(
        f"/unit-operations/{DEMO_SNAPSHOT_RUNNING_OPERATION_ID}/expected-remaining",
        json={"expected_remaining_minutes": 480},
    )
    snapshot = client.post("/replan-candidates", params=as_of).json()

    approval = client.post(
        "/replan-approvals",
        json={
            "parent_plan_id": snapshot["parent_plan_id"],
            "candidate_id": "EDD+OT",
            "candidate_as_of": snapshot["as_of"],
        },
    )

    assert approval.status_code == 201
    assert approval.json()["version"] == 2
    windows = client.get("/work-calendar", params=as_of).json()["overtime"]
    assert [(row["start_at"], row["end_at"]) for row in windows] == [
        ("2026-10-22T17:00:00+09:00", "2026-10-22T19:00:00+09:00")
    ]
    forecast = client.get("/forecast", params=as_of).json()
    gate = next(row for row in forecast["gates"] if row["lot_id"] == "LOT-101")
    # Overtime shortens the delay but cannot remove it: the LOT stays URGENT.
    assert gate["slack_minutes"] == -177
    assert gate["risk_level"] == "URGENT"
    assert forecast["plan_version"] == 2
