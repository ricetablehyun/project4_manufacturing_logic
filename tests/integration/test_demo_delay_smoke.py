from pathlib import Path

from fastapi.testclient import TestClient

from production_control.demo.bootstrap import (
    DEMO_SNAPSHOT_RUNNING_OPERATION_ID,
    initialize_demo_database,
)
from production_control.demo.prepare_delay_smoke import prepare_delay_smoke
from production_control.demo.runtime import create_demo_app


def test_delay_smoke_exposes_worker_input_then_replan_flow(tmp_path: Path) -> None:
    database_path = initialize_demo_database(tmp_path / "demo.db")
    reference_time = prepare_delay_smoke(database_path)
    client = TestClient(create_demo_app(database_path))

    waiting = client.get(
        "/forecast",
        params={"as_of": reference_time.isoformat()},
    )
    assert waiting.status_code == 200
    waiting_payload = waiting.json()
    assert waiting_payload["readiness"] == "WAIT"
    assert waiting_payload["waiting_operation_ids"] == [
        DEMO_SNAPSHOT_RUNNING_OPERATION_ID
    ]

    estimate = client.patch(
        f"/unit-operations/{DEMO_SNAPSHOT_RUNNING_OPERATION_ID}/expected-remaining",
        json={"expected_remaining_minutes": 480},
    )
    assert estimate.status_code == 200

    ready = client.get(
        "/forecast",
        params={"as_of": reference_time.isoformat()},
    )
    assert ready.status_code == 200
    ready_payload = ready.json()
    assert ready_payload["readiness"] == "READY"
    lot_001 = next(row for row in ready_payload["lots"] if row["lot_id"] == "LOT-101")
    assert lot_001["risk_level"] == "URGENT"
    assert {row["lot_id"] for row in ready_payload["lots"]} == {
        "LOT-101",
        "LOT-102",
        "LOT-103",
    }

    candidates = client.post(
        "/replan-candidates",
        params={"as_of": reference_time.isoformat()},
    )
    assert candidates.status_code == 200
    candidate_payload = candidates.json()
    assert candidate_payload["action"] == "GENERATE_CANDIDATES"
    assert [row["candidate_id"] for row in candidate_payload["candidates"]] == [
        "FCFS",
        "EDD",
        "SLACK",
        "CR",
    ]
    assert all("policy_compliant" in row for row in candidate_payload["candidates"])

    compliant = [
        row for row in candidate_payload["candidates"] if row["policy_compliant"] is True
    ]
    assert compliant
    assert candidate_payload["recommended_candidate_id"] in {
        row["candidate_id"] for row in compliant
    }

    # D075: the third presentation LOT exists specifically so the four dispatch
    # rules do not collapse into one indistinguishable result after urgent
    # LOT-001 keeps its hard-policy priority. At least two policy-compliant
    # alternatives must therefore produce different D029 KPI signatures.
    kpi_signatures = {
        (
            row["kpi"]["late_lot_count"],
            row["kpi"]["total_tardiness_minutes"],
            row["kpi"]["overtime_minutes"],
            row["kpi"]["change_count"],
        )
        for row in compliant
    }
    assert len(kpi_signatures) >= 2
