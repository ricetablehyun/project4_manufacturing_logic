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
from production_control.persistence.materialization import materialize_lot_execution

SEOUL = ZoneInfo("Asia/Seoul")


def dt(hour: int, minute: int = 0) -> datetime:
    return datetime(2026, 10, 5, hour, minute, tzinfo=SEOUL)


def seeded_client(tmp_path: Path) -> TestClient:
    engine = create_sqlite_engine(tmp_path / "unit_operation_api.db")
    create_schema(engine)
    session_factory = create_session_factory(engine)
    session = session_factory()
    seed_f02_fixture(session)
    materialize_lot_execution(session=session, lot_id="LOT-101")
    materialize_lot_execution(session=session, lot_id="LOT-102")
    session.close()
    return TestClient(create_app(session_factory=session_factory))


def test_unit_operation_api_returns_deterministic_operator_rows(tmp_path: Path) -> None:
    client = seeded_client(tmp_path)

    response = client.get("/unit-operations", params={"lot_id": "LOT-101"})

    assert response.status_code == 200
    payload = response.json()
    assert len(payload) == 20
    first = payload[0]
    assert first["lot_id"] == "LOT-101"
    assert first["unit_id"] == "LOT-101-U01"
    assert first["unit_code"] == "U01"
    assert first["routing_step_id"] == "STEP-01-TAPING"
    assert first["seq_no"] == 1
    assert first["process_code"] == "TAPING"
    assert first["state"] == "WAITING"
    assert first["attempt_no"] == 1
    assert first["active_minutes"] == 0.0
    assert first["result"] is None
    assert first["last_event_at"] is None


def test_unit_operation_api_reflects_persisted_work_event(tmp_path: Path) -> None:
    client = seeded_client(tmp_path)
    operation_id = "OP::LOT-101-U01::STEP-01-TAPING"

    event_response = client.post(
        "/work-events",
        json={
            "event_id": "EVT-UI-START-1",
            "unit_operation_id": operation_id,
            "event_type": "START",
            "occurred_at": dt(9).isoformat(),
            "station_code": None,
            "worker_code": None,
            "reason": None,
        },
    )
    assert event_response.status_code == 201

    response = client.get("/unit-operations", params={"lot_id": "LOT-101"})

    assert response.status_code == 200
    row = next(item for item in response.json() if item["operation_id"] == operation_id)
    assert row["state"] == "RUNNING"
    assert row["attempt_no"] == 1
    assert row["last_event_at"] == dt(9).isoformat()
