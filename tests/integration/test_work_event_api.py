from pathlib import Path

from fastapi.testclient import TestClient
from sqlalchemy import func, select

from production_control.api import create_app
from production_control.persistence.database import (
    create_schema,
    create_session_factory,
    create_sqlite_engine,
)
from production_control.persistence.fixture_seed import seed_f02_fixture
from production_control.persistence.materialization import materialize_lot_execution
from production_control.persistence.models import UnitOperationRow, WorkEventRow

OPERATION_ID = "OP::LOT-101-U01::STEP-01-TAPING"


def make_client(tmp_path: Path):
    engine = create_sqlite_engine(tmp_path / "work_event_api.db")
    create_schema(engine)
    session_factory = create_session_factory(engine)

    session = session_factory()
    try:
        seed_f02_fixture(session)
        materialize_lot_execution(session=session, lot_id="LOT-101")
    finally:
        session.close()

    client = TestClient(create_app(session_factory=session_factory))
    return client, session_factory


def start_payload(*, operation_id: str = OPERATION_ID) -> dict[str, object]:
    return {
        "event_id": "API-E1",
        "unit_operation_id": operation_id,
        "event_type": "START",
        "occurred_at": "2026-10-05T09:05:00+09:00",
        "station_code": "ASSEMBLY",
        "worker_code": "WORKER-A",
        "reason": None,
    }


def test_post_work_event_persists_and_returns_current_snapshot(tmp_path: Path) -> None:
    client, session_factory = make_client(tmp_path)

    response = client.post("/work-events", json=start_payload())

    assert response.status_code == 201
    assert response.json() == {
        "event_id": "API-E1",
        "duplicate": False,
        "operation_id": OPERATION_ID,
        "lot_id": "LOT-101",
        "unit_id": "LOT-101-U01",
        "process_code": "TAPING",
        "state": "RUNNING",
        "attempt_no": 1,
        "active_minutes": 0.0,
        "result": None,
    }

    session = session_factory()
    try:
        operation = session.get(UnitOperationRow, OPERATION_ID)
        event = session.get(WorkEventRow, "API-E1")
        assert operation is not None
        assert operation.state == "RUNNING"
        assert event is not None
        assert event.station_code == "ASSEMBLY"
        assert event.worker_code == "WORKER-A"
    finally:
        session.close()


def test_duplicate_event_returns_200_without_second_row(tmp_path: Path) -> None:
    client, session_factory = make_client(tmp_path)
    payload = start_payload()

    first = client.post("/work-events", json=payload)
    duplicate = client.post("/work-events", json=payload)

    assert first.status_code == 201
    assert duplicate.status_code == 200
    assert duplicate.json()["duplicate"] is True
    assert duplicate.json()["state"] == "RUNNING"

    session = session_factory()
    try:
        event_count = session.scalar(select(func.count()).select_from(WorkEventRow))
        assert event_count == 1
    finally:
        session.close()


def test_unknown_operation_returns_404(tmp_path: Path) -> None:
    client, _ = make_client(tmp_path)

    response = client.post(
        "/work-events",
        json=start_payload(operation_id="OP-DOES-NOT-EXIST"),
    )

    assert response.status_code == 404
    assert response.json()["detail"] == "unknown unit_operation_id: OP-DOES-NOT-EXIST"


def test_invalid_state_transition_returns_409_without_persisting(tmp_path: Path) -> None:
    client, session_factory = make_client(tmp_path)
    payload = start_payload()
    payload.update(
        {
            "event_type": "HOLD",
            "reason": "cannot hold before start",
            "expected_hold_minutes": 60,
        }
    )

    response = client.post("/work-events", json=payload)

    assert response.status_code == 409
    assert response.json()["detail"] == "HOLD requires RUNNING state"

    session = session_factory()
    try:
        event_count = session.scalar(select(func.count()).select_from(WorkEventRow))
        operation = session.get(UnitOperationRow, OPERATION_ID)
        assert event_count == 0
        assert operation is not None
        assert operation.state == "WAITING"
    finally:
        session.close()


def test_hold_requires_worker_expected_hold_minutes(tmp_path: Path) -> None:
    client, _ = make_client(tmp_path)
    started = client.post("/work-events", json=start_payload())
    assert started.status_code == 201

    response = client.post(
        "/work-events",
        json={
            "event_id": "API-E2",
            "unit_operation_id": OPERATION_ID,
            "event_type": "HOLD",
            "occurred_at": "2026-10-05T09:10:00+09:00",
            "station_code": "ASSEMBLY",
            "worker_code": "WORKER-A",
            "reason": "temporary tuning issue",
        },
    )

    assert response.status_code == 422


def test_hold_estimate_sets_and_resume_clears_hold_until(tmp_path: Path) -> None:
    client, session_factory = make_client(tmp_path)
    started = client.post("/work-events", json=start_payload())
    assert started.status_code == 201

    held = client.post(
        "/work-events",
        json={
            "event_id": "API-E2",
            "unit_operation_id": OPERATION_ID,
            "event_type": "HOLD",
            "occurred_at": "2026-10-05T09:10:00+09:00",
            "station_code": "ASSEMBLY",
            "worker_code": "WORKER-A",
            "reason": "temporary tuning issue",
            "expected_hold_minutes": 120,
        },
    )
    assert held.status_code == 201

    session = session_factory()
    try:
        operation = session.get(UnitOperationRow, OPERATION_ID)
        assert operation is not None
        assert operation.state == "HOLD"
        assert operation.hold_until.isoformat().startswith("2026-10-05T11:10")
    finally:
        session.close()

    resumed = client.post(
        "/work-events",
        json={
            "event_id": "API-E3",
            "unit_operation_id": OPERATION_ID,
            "event_type": "RESUME",
            "occurred_at": "2026-10-05T10:00:00+09:00",
            "station_code": "ASSEMBLY",
            "worker_code": "WORKER-A",
            "reason": None,
        },
    )
    assert resumed.status_code == 201

    session = session_factory()
    try:
        operation = session.get(UnitOperationRow, OPERATION_ID)
        assert operation is not None
        assert operation.state == "RUNNING"
        assert operation.hold_until is None
    finally:
        session.close()


def test_naive_occurred_at_is_rejected_as_422(tmp_path: Path) -> None:
    client, _ = make_client(tmp_path)
    payload = start_payload()
    payload["occurred_at"] = "2026-10-05T09:05:00"

    response = client.post("/work-events", json=payload)

    assert response.status_code == 422
