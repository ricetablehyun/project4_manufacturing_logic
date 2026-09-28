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
PLAN_ID = "PLAN-APPROVAL-API-1"
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
    engine = create_sqlite_engine(tmp_path / "replan_approval_api.db")
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


def approval_payload(*, candidate_id: str = "EDD") -> dict[str, str]:
    return {
        "parent_plan_id": PLAN_ID,
        "candidate_id": candidate_id,
        "candidate_as_of": dt(9, 5).isoformat(),
    }


def test_approval_persists_selected_candidate_and_closes_forecast_loop(tmp_path: Path) -> None:
    client, session_factory = seeded_client(tmp_path, urgent=True)

    response = client.post("/replan-approvals", json=approval_payload(candidate_id="EDD"))

    assert response.status_code == 201
    payload = response.json()
    assert payload["plan_id"].startswith("REPLAN-")
    assert payload["version"] == 2
    assert payload["status"] == "APPROVED"
    assert payload["parent_plan_id"] == PLAN_ID
    assert payload["priority_rule"] == "EDD"
    assert payload["selected_candidate_id"] == "EDD"

    session = session_factory()
    try:
        plan_count = session.scalar(select(func.count()).select_from(SchedulePlanRow))
        task_count = session.scalar(select(func.count()).select_from(ScheduleTaskRow))
        assert plan_count == 2
        assert task_count == 20

        persisted = session.get(SchedulePlanRow, payload["plan_id"])
        assert persisted is not None
        assert persisted.version == 2
        assert persisted.parent_plan_id == PLAN_ID
        assert persisted.status == "APPROVED"
    finally:
        session.close()

    forecast = client.get(
        "/forecast",
        params={"as_of": dt(9, 5).isoformat()},
    )
    assert forecast.status_code == 200
    forecast_payload = forecast.json()
    assert forecast_payload["plan_id"] == payload["plan_id"]
    assert forecast_payload["plan_version"] == 2


def test_approval_rejects_stale_parent_after_plan_changes(tmp_path: Path) -> None:
    client, _ = seeded_client(tmp_path, urgent=True)

    first = client.post("/replan-approvals", json=approval_payload(candidate_id="FCFS"))
    assert first.status_code == 201

    stale = client.post("/replan-approvals", json=approval_payload(candidate_id="EDD"))

    assert stale.status_code == 409
    assert "parent plan is no longer current" in stale.json()["detail"]


def test_approval_rejects_execution_newer_than_candidate_snapshot(tmp_path: Path) -> None:
    client, _ = seeded_client(tmp_path, urgent=True)
    started = client.post(
        "/work-events",
        json={
            "event_id": "APPROVAL-TAPING-START",
            "unit_operation_id": "OP::LOT-101-U01::STEP-01-TAPING",
            "event_type": "START",
            "occurred_at": dt(9, 6).isoformat(),
            "station_code": "ASSEMBLY",
            "worker_code": "WORKER-A",
            "reason": None,
        },
    )
    assert started.status_code == 201

    response = client.post("/replan-approvals", json=approval_payload(candidate_id="EDD"))

    assert response.status_code == 409
    assert "as_of cannot be earlier than the latest persisted WorkEvent" in response.json()[
        "detail"
    ]


def test_approval_rejects_unknown_candidate_id(tmp_path: Path) -> None:
    client, _ = seeded_client(tmp_path, urgent=True)

    response = client.post(
        "/replan-approvals",
        json=approval_payload(candidate_id="NOT-A-RULE"),
    )

    assert response.status_code == 404
    assert response.json()["detail"] == "unknown replan candidate_id: NOT-A-RULE"


def test_approval_rejects_snapshot_that_is_no_longer_replan_urgent(tmp_path: Path) -> None:
    client, _ = seeded_client(tmp_path, urgent=False)

    response = client.post("/replan-approvals", json=approval_payload(candidate_id="EDD"))

    assert response.status_code == 409
    assert "current policy no longer generates candidates" in response.json()["detail"]


def test_approval_rejects_timezone_naive_candidate_as_of(tmp_path: Path) -> None:
    client, _ = seeded_client(tmp_path, urgent=True)
    payload = approval_payload(candidate_id="EDD")
    payload["candidate_as_of"] = "2026-10-05T09:05:00"

    response = client.post("/replan-approvals", json=payload)

    assert response.status_code == 422
