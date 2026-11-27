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
