from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from fastapi.testclient import TestClient

from production_control.api.app import create_app
from production_control.persistence.database import (
    create_schema,
    create_session_factory,
    create_sqlite_engine,
)
from production_control.persistence.fixture_seed import seed_f02_fixture
from production_control.persistence.live_forecast import LiveForecastConfig
from production_control.persistence.materialization import materialize_lot_execution
from production_control.persistence.models import SchedulePlanRow, ScheduleTaskRow

SEOUL = ZoneInfo("Asia/Seoul")
PLAN_ID = "PLAN-LIVE-1"
TAPING_OPERATION_ID = "OP::LOT-101-U01::STEP-01-TAPING"
INTERNAL_STEPS = (
    "STEP-01-TAPING",
    "STEP-03-GENERAL-ASSEMBLY",
    "STEP-04-TUNING",
    "STEP-05-FINISH-ASSEMBLY",
    "STEP-06-FINAL-TEST",
)


def dt(hour: int, minute: int = 0) -> datetime:
    return datetime(2026, 10, 5, hour, minute, tzinfo=SEOUL)


def seeded_client(tmp_path: Path) -> TestClient:
    engine = create_sqlite_engine(tmp_path / "live_forecast_api.db")
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
    return TestClient(app)


def process_forecast(payload: dict, *, lot_id: str, process_code: str) -> dict:
    return next(
        forecast
        for forecast in payload["processes"]
        if forecast["lot_id"] == lot_id
        and forecast["process_code"] == process_code
    )


def start_first_taping(client: TestClient) -> None:
    accepted = client.post(
        "/work-events",
        json={
            "event_id": "LIVE-TAPING-START",
            "unit_operation_id": TAPING_OPERATION_ID,
            "event_type": "START",
            "occurred_at": dt(9).isoformat(),
            "station_code": "ASSEMBLY",
            "worker_code": "WORKER-A",
            "reason": None,
        },
    )
    assert accepted.status_code == 201


def test_get_forecast_uses_current_approved_plan_and_explicit_as_of(
    tmp_path: Path,
) -> None:
    client = seeded_client(tmp_path)

    response = client.get(
        "/forecast",
        params={"as_of": dt(9, 5).isoformat()},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["plan_id"] == PLAN_ID
    assert payload["plan_version"] == 1
    assert payload["as_of"] == dt(9, 5).isoformat()
    assert payload["readiness"] == "READY"
    assert {item["lot_id"] for item in payload["lots"]} == {"LOT-101", "LOT-102"}
    assert len(payload["processes"]) == 10
    assert {item["gate_id"] for item in payload["gates"]} == {
        "GATE-LOT-101-SHIPPING-INSPECTION",
        "GATE-LOT-102-SHIPPING-INSPECTION",
    }
    assert payload["missing_gate_ids"] == []
    assert payload["waiting_operation_ids"] == []


def test_work_event_changes_live_forecast_at_same_reference_time(
    tmp_path: Path,
) -> None:
    client = seeded_client(tmp_path)
    params = {"as_of": dt(9, 5).isoformat()}

    before = client.get("/forecast", params=params)
    assert before.status_code == 200
    before_taping = process_forecast(
        before.json(),
        lot_id="LOT-101",
        process_code="TAPING",
    )

    start_first_taping(client)

    after = client.get("/forecast", params=params)
    assert after.status_code == 200
    after_taping = process_forecast(
        after.json(),
        lot_id="LOT-101",
        process_code="TAPING",
    )

    assert after.json()["readiness"] == "READY"
    assert after_taping["forecast_end"] != before_taping["forecast_end"]


def test_running_over_pace_exposes_actionable_unit_operation_id(
    tmp_path: Path,
) -> None:
    client = seeded_client(tmp_path)
    start_first_taping(client)

    response = client.get(
        "/forecast",
        params={"as_of": dt(9, 11).isoformat()},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["readiness"] == "WAIT"
    assert payload["lots"] == []
    assert payload["gates"] == []
    assert payload["processes"] == []
    assert payload["waiting_operation_ids"] == [TAPING_OPERATION_ID]


def test_worker_remaining_estimate_resumes_forecast(tmp_path: Path) -> None:
    client = seeded_client(tmp_path)
    start_first_taping(client)

    waiting = client.get(
        "/forecast",
        params={"as_of": dt(9, 11).isoformat()},
    )
    assert waiting.status_code == 200
    assert waiting.json()["readiness"] == "WAIT"

    updated = client.patch(
        f"/unit-operations/{TAPING_OPERATION_ID}/expected-remaining",
        json={"expected_remaining_minutes": 7},
    )
    assert updated.status_code == 200

    resumed = client.get(
        "/forecast",
        params={"as_of": dt(9, 11).isoformat()},
    )
    assert resumed.status_code == 200
    payload = resumed.json()
    assert payload["readiness"] == "READY"
    assert payload["waiting_operation_ids"] == []
    assert payload["lots"]
    assert payload["processes"]


def test_forecast_rejects_timezone_naive_as_of(tmp_path: Path) -> None:
    client = seeded_client(tmp_path)

    response = client.get(
        "/forecast",
        params={"as_of": "2026-10-05T09:05:00"},
    )

    assert response.status_code == 422
    assert response.json()["detail"] == "as_of must be timezone-aware"
