from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from fastapi.testclient import TestClient
from sqlalchemy import func, select

from production_control.api.app import create_app
from production_control.persistence.database import (
    create_schema,
    create_session_factory,
    create_sqlite_engine,
)
from production_control.persistence.fixture_seed import seed_f02_fixture
from production_control.persistence.live_forecast import LiveForecastConfig
from production_control.persistence.materialization import materialize_lot_execution
from production_control.persistence.models import (
    InspectionGateRow,
    SchedulePlanRow,
    ScheduleTaskRow,
)

SEOUL = ZoneInfo("Asia/Seoul")
PLAN_ID = "PLAN-REPLAN-API-1"
INTERNAL_STEPS = (
    "STEP-01-TAPING",
    "STEP-03-GENERAL-ASSEMBLY",
    "STEP-04-TUNING",
    "STEP-05-FINISH-ASSEMBLY",
    "STEP-06-FINAL-TEST",
)


def dt(hour: int, minute: int = 0, *, day: int = 5) -> datetime:
    return datetime(2026, 10, day, hour, minute, tzinfo=SEOUL)


def seeded_client(tmp_path: Path, *, urgent: bool) -> tuple[TestClient, object]:
    engine = create_sqlite_engine(tmp_path / "replan_candidate_api.db")
    create_schema(engine)
    session_factory = create_session_factory(engine)
    session = session_factory()
    seed_f02_fixture(session)
    for lot_id in ("LOT-101", "LOT-102"):
        materialize_lot_execution(session=session, lot_id=lot_id)

    session.add(
        SchedulePlanRow(
            plan_id=PLAN_ID,
            version=1,
            plan_kind="BASELINE",
            priority_rule="EDD",
            status="APPROVED",
            parent_plan_id=None,
            trigger_reason=None,
            created_at=dt(8),
            approved_at=dt(8, 30),
            late_lot_count=0,
            total_tardiness_minutes=0,
            overtime_minutes=0,
            change_count=0,
        )
    )
    rank = 1
    for lot_id in ("LOT-101", "LOT-102"):
        for step_id in INTERNAL_STEPS:
            session.add(
                ScheduleTaskRow(
                    schedule_task_id=f"TASK::{lot_id}::{step_id}",
                    plan_id=PLAN_ID,
                    lot_id=lot_id,
                    routing_step_id=step_id,
                    target_start=dt(9),
                    target_end=dt(17),
                    target_qty=4,
                    priority_rank=rank,
                )
            )
            rank += 1

    gate_101 = session.get(
        InspectionGateRow,
        "GATE-LOT-101-SHIPPING-INSPECTION",
    )
    gate_102 = session.get(
        InspectionGateRow,
        "GATE-LOT-102-SHIPPING-INSPECTION",
    )
    assert gate_101 is not None
    assert gate_102 is not None
    if urgent:
        gate_101.planned_at = dt(9, 30)
        gate_102.planned_at = dt(9, 45)
    else:
        gate_101.planned_at = dt(17, day=7)
        gate_102.planned_at = dt(17, day=7)

    session.commit()
    session.close()

    app = create_app(
        session_factory=session_factory,
        forecast_config=LiveForecastConfig(
            calendar_id="CALENDAR-NORMAL",
            pace_min_samples=3,
            warning_threshold_minutes=120,
        ),
    )
    return TestClient(app), session_factory


def test_urgent_replan_returns_four_transient_candidates_with_tasks(tmp_path: Path) -> None:
    client, session_factory = seeded_client(tmp_path, urgent=True)

    response = client.post(
        "/replan-candidates",
        params={"as_of": dt(9, 5).isoformat()},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["parent_plan_id"] == PLAN_ID
    assert payload["parent_plan_version"] == 1
    assert payload["risk_level"] == "URGENT"
    assert payload["action"] == "GENERATE_CANDIDATES"
    assert payload["requires_manager_approval"] is True

    candidate_ids = [candidate["candidate_id"] for candidate in payload["candidates"]]
    assert candidate_ids == ["FCFS", "EDD", "SLACK", "CR"]
    assert payload["recommended_candidate_id"] in candidate_ids

    for candidate in payload["candidates"]:
        assert candidate["rule"] == candidate["candidate_id"]
        assert len(candidate["tasks"]) == 10
        assert all(task["target_qty"] == 4 for task in candidate["tasks"])
        assert all(task["priority_rank"] > 0 for task in candidate["tasks"])
        assert set(candidate["kpi"]) == {
            "late_lot_count",
            "total_tardiness_minutes",
            "overtime_minutes",
            "change_count",
        }

    session = session_factory()
    try:
        plan_count = session.scalar(select(func.count()).select_from(SchedulePlanRow))
        task_count = session.scalar(select(func.count()).select_from(ScheduleTaskRow))
        assert plan_count == 1
        assert task_count == 10
    finally:
        session.close()


def test_normal_replan_policy_returns_no_candidates(tmp_path: Path) -> None:
    client, _ = seeded_client(tmp_path, urgent=False)

    response = client.post(
        "/replan-candidates",
        params={"as_of": dt(9, 5).isoformat()},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["risk_level"] == "NORMAL"
    assert payload["action"] == "KEEP_PLAN"
    assert payload["candidates"] == []
    assert payload["recommended_candidate_id"] is None
    assert payload["requires_manager_approval"] is False


def test_replan_rejects_live_forecast_wait_state(tmp_path: Path) -> None:
    client, _ = seeded_client(tmp_path, urgent=True)
    started = client.post(
        "/work-events",
        json={
            "event_id": "REPLAN-TAPING-START",
            "unit_operation_id": "OP::LOT-101-U01::STEP-01-TAPING",
            "event_type": "START",
            "occurred_at": dt(9).isoformat(),
            "station_code": "ASSEMBLY",
            "worker_code": "WORKER-A",
            "reason": None,
        },
    )
    assert started.status_code == 201

    response = client.post(
        "/replan-candidates",
        params={"as_of": dt(9, 11).isoformat()},
    )

    assert response.status_code == 409
    assert "replanning requires READY Live Forecast" in response.json()["detail"]


def test_replan_rejects_timezone_naive_as_of(tmp_path: Path) -> None:
    client, _ = seeded_client(tmp_path, urgent=True)

    response = client.post(
        "/replan-candidates",
        params={"as_of": "2026-10-05T09:05:00"},
    )

    assert response.status_code == 422
    assert response.json()["detail"] == "as_of must be timezone-aware"
