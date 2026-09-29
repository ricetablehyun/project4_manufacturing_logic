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
OPERATION_ID = "OP::LOT-101-U01::STEP-01-TAPING"


def dt(hour: int, minute: int = 0) -> datetime:
    return datetime(2026, 10, 5, hour, minute, tzinfo=SEOUL)


def seeded_client(tmp_path: Path) -> TestClient:
    engine = create_sqlite_engine(tmp_path / "expected_remaining_api.db")
    create_schema(engine)
    session_factory = create_session_factory(engine)
    session = session_factory()
    seed_f02_fixture(session)
    materialize_lot_execution(session=session, lot_id="LOT-101")
    session.close()
    return TestClient(create_app(session_factory=session_factory))


def start_operation(client: TestClient) -> None:
    response = client.post(
        "/work-events",
        json={
            "event_id": "EVT-START",
            "unit_operation_id": OPERATION_ID,
            "event_type": "START",
            "occurred_at": dt(9).isoformat(),
            "station_code": None,
            "worker_code": None,
            "reason": None,
        },
    )
    assert response.status_code == 201


def test_expected_remaining_is_rejected_for_non_running_operation(tmp_path: Path) -> None:
    client = seeded_client(tmp_path)

    response = client.patch(
        f"/unit-operations/{OPERATION_ID}/expected-remaining",
        json={"expected_remaining_minutes": 15},
    )

    assert response.status_code == 409
    assert "RUNNING" in response.json()["detail"]


def test_worker_expected_remaining_is_visible_and_cleared_by_next_event(
    tmp_path: Path,
) -> None:
    client = seeded_client(tmp_path)
    start_operation(client)

    updated = client.patch(
        f"/unit-operations/{OPERATION_ID}/expected-remaining",
        json={"expected_remaining_minutes": 18},
    )
    assert updated.status_code == 200
    assert updated.json()["expected_remaining_minutes"] == 18.0

    rows = client.get("/unit-operations", params={"lot_id": "LOT-101"})
    assert rows.status_code == 200
    row = next(item for item in rows.json() if item["operation_id"] == OPERATION_ID)
    assert row["expected_remaining_minutes"] == 18.0

    held = client.post(
        "/work-events",
        json={
            "event_id": "EVT-HOLD",
            "unit_operation_id": OPERATION_ID,
            "event_type": "HOLD",
            "occurred_at": dt(9, 5).isoformat(),
            "station_code": None,
            "worker_code": None,
            "reason": "unexpected adjustment needed",
            "expected_hold_minutes": 60,
        },
    )
    assert held.status_code == 201

    rows = client.get("/unit-operations", params={"lot_id": "LOT-101"})
    row = next(item for item in rows.json() if item["operation_id"] == OPERATION_ID)
    assert row["state"] == "HOLD"
    assert row["expected_remaining_minutes"] is None


def test_expected_remaining_must_be_positive(tmp_path: Path) -> None:
    client = seeded_client(tmp_path)
    start_operation(client)

    response = client.patch(
        f"/unit-operations/{OPERATION_ID}/expected-remaining",
        json={"expected_remaining_minutes": 0},
    )

    assert response.status_code == 422
