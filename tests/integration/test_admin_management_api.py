from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from fastapi.testclient import TestClient
from sqlalchemy import select

from production_control.api.app import create_app
from production_control.persistence.database import (
    create_schema,
    create_session_factory,
    create_sqlite_engine,
)
from production_control.persistence.fixture_seed import seed_f02_fixture
from production_control.persistence.materialization import materialize_lot_execution
from production_control.persistence.models import (
    InspectionGateRow,
    LotRow,
    UnitOperationRow,
    UnitRow,
)

SEOUL = ZoneInfo("Asia/Seoul")


def dt(day: int, hour: int, minute: int = 0) -> datetime:
    return datetime(2026, 10, day, hour, minute, tzinfo=SEOUL)


def seeded_client(tmp_path: Path) -> tuple[TestClient, object]:
    engine = create_sqlite_engine(tmp_path / "admin_management_api.db")
    create_schema(engine)
    session_factory = create_session_factory(engine)
    session = session_factory()
    seed_f02_fixture(session)
    session.close()
    return TestClient(create_app(session_factory=session_factory)), session_factory


def materialize_lot(session_factory: object, lot_id: str) -> None:
    session = session_factory()  # type: ignore[operator]
    try:
        materialize_lot_execution(session=session, lot_id=lot_id)
    finally:
        session.close()


def lot_operations(session: object, lot_id: str) -> list[UnitOperationRow]:
    return list(
        session.scalars(  # type: ignore[attr-defined]
            select(UnitOperationRow)
            .join(UnitRow, UnitOperationRow.unit_id == UnitRow.unit_id)
            .where(UnitRow.lot_id == lot_id)
            .order_by(UnitOperationRow.unit_operation_id)
        ).all()
    )


def test_get_lots_returns_stable_admin_snapshot(tmp_path: Path) -> None:
    client, _ = seeded_client(tmp_path)

    response = client.get("/lots")

    assert response.status_code == 200
    payload = response.json()
    assert [lot["lot_id"] for lot in payload] == ["LOT-101", "LOT-102"]
    assert payload[0]["product_id"] == "PRODUCT-RF-MOCK-A"
    assert payload[0]["quantity"] == 4
    assert payload[0]["status"] == "ACTIVE"


def test_patch_lot_updates_only_allowed_fields(tmp_path: Path) -> None:
    client, session_factory = seeded_client(tmp_path)

    response = client.patch(
        "/lots/LOT-101",
        json={
            "release_at": dt(5, 10).isoformat(),
            "due_at": dt(7, 14).isoformat(),
            "status": "HOLD",
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert datetime.fromisoformat(payload["release_at"]) == dt(5, 10)
    assert datetime.fromisoformat(payload["due_at"]) == dt(7, 14)
    assert payload["status"] == "HOLD"
    assert payload["product_id"] == "PRODUCT-RF-MOCK-A"
    assert payload["quantity"] == 4

    session = session_factory()
    try:
        row = session.get(LotRow, "LOT-101")
        assert row is not None
        assert row.release_at == dt(5, 10)
        assert row.due_at == dt(7, 14)
        assert row.status == "HOLD"
        assert row.product_id == "PRODUCT-RF-MOCK-A"
        assert row.quantity == 4
    finally:
        session.close()


def test_patch_lot_release_syncs_materialized_operation_eligibility(tmp_path: Path) -> None:
    client, session_factory = seeded_client(tmp_path)
    materialize_lot(session_factory, "LOT-101")

    response = client.patch(
        "/lots/LOT-101",
        json={"release_at": dt(5, 10).isoformat()},
    )

    assert response.status_code == 200
    assert datetime.fromisoformat(response.json()["release_at"]) == dt(5, 10)

    session = session_factory()
    try:
        operations = lot_operations(session, "LOT-101")
        assert operations
        assert all(operation.eligible_at == dt(5, 10) for operation in operations)
    finally:
        session.close()


def test_patch_lot_release_rejects_after_work_event_without_partial_update(
    tmp_path: Path,
) -> None:
    client, session_factory = seeded_client(tmp_path)
    materialize_lot(session_factory, "LOT-101")

    event_response = client.post(
        "/work-events",
        json={
            "event_id": "E-LOT-101-START",
            "unit_operation_id": "OP::LOT-101-U01::STEP-01-TAPING",
            "event_type": "START",
            "occurred_at": dt(5, 9, 5).isoformat(),
            "station_code": "ASSEMBLY",
            "worker_code": "WORKER-A",
            "reason": None,
        },
    )
    assert event_response.status_code == 201

    response = client.patch(
        "/lots/LOT-101",
        json={
            "release_at": dt(5, 10).isoformat(),
            "due_at": dt(7, 14).isoformat(),
        },
    )

    assert response.status_code == 409
    assert response.json()["detail"] == (
        "release_at cannot be changed after WorkEvent exists for lot_id: LOT-101"
    )

    session = session_factory()
    try:
        row = session.get(LotRow, "LOT-101")
        assert row is not None
        assert row.release_at == dt(5, 9)
        assert row.due_at == dt(6, 12)
        operations = lot_operations(session, "LOT-101")
        assert operations
        assert all(operation.eligible_at == dt(5, 9) for operation in operations)
    finally:
        session.close()


def test_patch_lot_returns_404_for_unknown_lot(tmp_path: Path) -> None:
    client, _ = seeded_client(tmp_path)

    response = client.patch("/lots/LOT-404", json={"status": "ACTIVE"})

    assert response.status_code == 404
    assert response.json()["detail"] == "unknown lot_id: LOT-404"


def test_patch_lot_rejects_protected_structural_fields(tmp_path: Path) -> None:
    client, _ = seeded_client(tmp_path)

    response = client.patch("/lots/LOT-101", json={"quantity": 99})

    assert response.status_code == 422


def test_patch_lot_rejects_timezone_naive_datetime(tmp_path: Path) -> None:
    client, _ = seeded_client(tmp_path)

    response = client.patch(
        "/lots/LOT-101",
        json={"due_at": "2026-10-07T14:00:00"},
    )

    assert response.status_code == 422


def test_get_inspection_gates_supports_lot_filter(tmp_path: Path) -> None:
    client, _ = seeded_client(tmp_path)

    all_response = client.get("/inspection-gates")
    filtered_response = client.get(
        "/inspection-gates",
        params={"lot_id": "LOT-101"},
    )

    assert all_response.status_code == 200
    assert [gate["gate_id"] for gate in all_response.json()] == [
        "GATE-LOT-101-SHIPPING-INSPECTION",
        "GATE-LOT-102-SHIPPING-INSPECTION",
    ]
    assert filtered_response.status_code == 200
    filtered = filtered_response.json()
    assert len(filtered) == 1
    assert filtered[0]["lot_id"] == "LOT-101"


def test_patch_inspection_gate_updates_allowed_fields_and_can_clear_completion(
    tmp_path: Path,
) -> None:
    client, session_factory = seeded_client(tmp_path)
    gate_id = "GATE-LOT-101-SHIPPING-INSPECTION"

    updated = client.patch(
        f"/inspection-gates/{gate_id}",
        json={
            "planned_at": dt(7, 11).isoformat(),
            "completed_at": dt(7, 10, 30).isoformat(),
            "status": "COMPLETED",
        },
    )
    cleared = client.patch(
        f"/inspection-gates/{gate_id}",
        json={"completed_at": None, "status": "PLANNED"},
    )

    assert updated.status_code == 200
    assert datetime.fromisoformat(updated.json()["planned_at"]) == dt(7, 11)
    assert datetime.fromisoformat(updated.json()["completed_at"]) == dt(7, 10, 30)
    assert updated.json()["status"] == "COMPLETED"
    assert updated.json()["lot_id"] == "LOT-101"
    assert updated.json()["gate_type"] == "SHIPPING_INSPECTION"

    assert cleared.status_code == 200
    assert cleared.json()["completed_at"] is None
    assert cleared.json()["status"] == "PLANNED"

    session = session_factory()
    try:
        row = session.get(InspectionGateRow, gate_id)
        assert row is not None
        assert row.planned_at == dt(7, 11)
        assert row.completed_at is None
        assert row.status == "PLANNED"
        assert row.lot_id == "LOT-101"
        assert row.gate_type == "SHIPPING_INSPECTION"
        assert row.required_after_step_id == "STEP-06-FINAL-TEST"
    finally:
        session.close()


def test_patch_inspection_gate_returns_404_for_unknown_gate(tmp_path: Path) -> None:
    client, _ = seeded_client(tmp_path)

    response = client.patch(
        "/inspection-gates/GATE-404",
        json={"status": "PLANNED"},
    )

    assert response.status_code == 404
    assert response.json()["detail"] == "unknown gate_id: GATE-404"


def test_patch_inspection_gate_rejects_protected_structural_fields(tmp_path: Path) -> None:
    client, _ = seeded_client(tmp_path)

    response = client.patch(
        "/inspection-gates/GATE-LOT-101-SHIPPING-INSPECTION",
        json={"gate_type": "OTHER"},
    )

    assert response.status_code == 422


def test_patch_inspection_gate_rejects_timezone_naive_datetime(tmp_path: Path) -> None:
    client, _ = seeded_client(tmp_path)

    response = client.patch(
        "/inspection-gates/GATE-LOT-101-SHIPPING-INSPECTION",
        json={"planned_at": "2026-10-07T11:00:00"},
    )

    assert response.status_code == 422
