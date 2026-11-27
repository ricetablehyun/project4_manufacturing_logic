"""Pin the exact KPI values shown in the midterm presentation.

The midterm presentation reported, for the D072 delay smoke (U030 tuning still
RUNNING, worker enters 480 expected remaining minutes):

- LOT-001 (LOT-101) production completion 4h57m after its shipping-inspection
  Gate start;
- EDD / Slack / CR: 1 late LOT, total Gate tardiness 4h57m (297 minutes);
- FCFS: 2 late LOTs, total Gate tardiness 9h09m (549 minutes).

The tardiness KPI in this system is measured against the shipping-inspection
Gate (``InspectionGate.planned_at``), i.e. it is a *shipping-inspection entry
delay*, not lateness against the customer due date (``Lot.due_at``). This test
keeps both the numbers and that distinction from drifting silently.
"""

from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from fastapi.testclient import TestClient

from production_control.demo.bootstrap import (
    DEMO_SNAPSHOT_RUNNING_OPERATION_ID,
    initialize_demo_database,
)
from production_control.demo.prepare_delay_smoke import prepare_delay_smoke
from production_control.demo.runtime import create_demo_app

SEOUL = ZoneInfo("Asia/Seoul")


def test_midterm_delay_smoke_kpis_are_reproduced_exactly(tmp_path: Path) -> None:
    database_path = initialize_demo_database(tmp_path / "demo.db")
    reference_time = prepare_delay_smoke(database_path)
    client = TestClient(create_demo_app(database_path))
    as_of = {"as_of": reference_time.isoformat()}

    estimate = client.patch(
        f"/unit-operations/{DEMO_SNAPSHOT_RUNNING_OPERATION_ID}/expected-remaining",
        json={"expected_remaining_minutes": 480},
    )
    assert estimate.status_code == 200

    forecast = client.get("/forecast", params=as_of)
    assert forecast.status_code == 200
    payload = forecast.json()
    assert payload["readiness"] == "READY"

    gate = next(row for row in payload["gates"] if row["lot_id"] == "LOT-101")
    assert gate["gate_type"] == "SHIPPING_INSPECTION"
    planned_at = datetime.fromisoformat(gate["planned_at"])
    forecast_at = datetime.fromisoformat(gate["forecast_at"])
    assert planned_at == datetime(2026, 10, 23, 9, 0, tzinfo=SEOUL)
    assert forecast_at == datetime(2026, 10, 23, 13, 57, tzinfo=SEOUL)
    assert (forecast_at - planned_at).total_seconds() / 60 == 297
    assert gate["slack_minutes"] == -297
    assert gate["risk_level"] == "URGENT"

    # The customer due date is a different, later reference point.
    lots = {row["lot_id"]: row for row in client.get("/lots").json()}
    customer_due_at = datetime.fromisoformat(lots["LOT-101"]["due_at"])
    assert customer_due_at == datetime(2026, 10, 29, 17, 0, tzinfo=SEOUL)
    assert customer_due_at > planned_at

    candidates = client.post("/replan-candidates", params=as_of)
    assert candidates.status_code == 200
    candidate_payload = candidates.json()
    kpis = {
        row["candidate_id"]: (
            row["policy_compliant"],
            row["kpi"]["late_lot_count"],
            row["kpi"]["total_tardiness_minutes"],
            row["kpi"]["overtime_minutes"],
        )
        for row in candidate_payload["candidates"]
    }
    assert kpis == {
        "FCFS": (True, 2, 549.0, 0.0),
        "EDD": (True, 1, 297.0, 0.0),
        "SLACK": (True, 1, 297.0, 0.0),
        "CR": (True, 1, 297.0, 0.0),
    }
    assert candidate_payload["recommended_candidate_id"] == "EDD"
