"""An approved replan must produce the KPI the manager saw when approving it.

Before the frozen-LOT-order fix, approving the FCFS candidate of the midterm
delay smoke (shown as 2 late LOTs / 549 min) produced a plan whose Live
Forecast was 1 late LOT / 297 min, because the LOT x process rank list could
not reproduce the candidate's dispatch order.
"""

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from production_control.demo.bootstrap import (
    DEMO_SNAPSHOT_RUNNING_OPERATION_ID,
    initialize_demo_database,
)
from production_control.demo.prepare_delay_smoke import prepare_delay_smoke
from production_control.demo.runtime import create_demo_app


def _gate_kpi(forecast_payload: dict) -> tuple[int, float]:
    late_lots = {
        gate["lot_id"] for gate in forecast_payload["gates"] if gate["slack_minutes"] < 0
    }
    tardiness = sum(max(-gate["slack_minutes"], 0.0) for gate in forecast_payload["gates"])
    return len(late_lots), tardiness


@pytest.mark.parametrize("candidate_id", ["FCFS", "EDD", "SLACK", "CR"])
def test_approved_candidate_forecast_matches_evaluated_kpi(
    tmp_path: Path,
    candidate_id: str,
) -> None:
    database_path = initialize_demo_database(tmp_path / "demo.db")
    reference_time = prepare_delay_smoke(database_path)
    client = TestClient(create_demo_app(database_path))
    as_of = {"as_of": reference_time.isoformat()}
    client.patch(
        f"/unit-operations/{DEMO_SNAPSHOT_RUNNING_OPERATION_ID}/expected-remaining",
        json={"expected_remaining_minutes": 480},
    )

    candidates = client.post("/replan-candidates", params=as_of).json()
    selected = next(
        row for row in candidates["candidates"] if row["candidate_id"] == candidate_id
    )
    approval = client.post(
        "/replan-approvals",
        json={
            "parent_plan_id": candidates["parent_plan_id"],
            "candidate_id": candidate_id,
            "candidate_as_of": reference_time.isoformat(),
        },
    )
    assert approval.status_code == 201

    current = client.get("/schedule-plan/current").json()
    assert current["plan_id"] == approval.json()["plan_id"]
    assert current["lot_priority_order"]
    assert sorted(current["lot_priority_order"]) == ["LOT-101", "LOT-102", "LOT-103"]

    forecast = client.get("/forecast", params=as_of).json()
    assert forecast["plan_id"] == approval.json()["plan_id"]
    assert _gate_kpi(forecast) == (
        selected["kpi"]["late_lot_count"],
        selected["kpi"]["total_tardiness_minutes"],
    )
