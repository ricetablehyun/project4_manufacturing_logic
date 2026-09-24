from sqlalchemy import func, select

from production_control.persistence.database import (
    create_schema,
    create_session_factory,
    create_sqlite_engine,
)
from production_control.persistence.fixture_seed import seed_f02_fixture
from production_control.persistence.materialization import materialize_lot_execution
from production_control.persistence.models import (
    LotRow,
    UnitOperationRow,
    WorkAttemptRow,
)


def seeded_session():
    engine = create_sqlite_engine()
    create_schema(engine)
    session = create_session_factory(engine)()
    seed_f02_fixture(session)
    return session


def test_f02_lot_materializes_only_internal_unit_time_steps() -> None:
    session = seeded_session()

    result = materialize_lot_execution(session=session, lot_id="LOT-101")

    assert result.created_operations == 20
    assert result.created_attempts == 20

    operations = session.scalars(
        select(UnitOperationRow).order_by(UnitOperationRow.unit_operation_id)
    ).all()
    assert len(operations) == 20
    assert {
        operation.routing_step_id for operation in operations
    } == {
        "STEP-01-TAPING",
        "STEP-03-GENERAL-ASSEMBLY",
        "STEP-04-TUNING",
        "STEP-05-FINISH-ASSEMBLY",
        "STEP-06-FINAL-TEST",
    }
    assert all(
        operation.routing_step_id != "STEP-02-EXTERNAL-FEED-BONDING"
        for operation in operations
    )


def test_materialized_operations_start_waiting_with_attempt_one() -> None:
    session = seeded_session()
    materialize_lot_execution(session=session, lot_id="LOT-101")

    lot = session.get(LotRow, "LOT-101")
    assert lot is not None

    operations = session.scalars(select(UnitOperationRow)).all()
    attempts = session.scalars(select(WorkAttemptRow)).all()

    assert len(operations) == 20
    assert len(attempts) == 20
    assert all(operation.state == "WAITING" for operation in operations)
    assert all(operation.current_attempt_no == 1 for operation in operations)
    assert all(operation.eligible_at == lot.release_at for operation in operations)
    assert all(attempt.attempt_no == 1 for attempt in attempts)
    assert all(attempt.active_minutes == 0 for attempt in attempts)


def test_materialization_is_idempotent() -> None:
    session = seeded_session()

    first = materialize_lot_execution(session=session, lot_id="LOT-101")
    second = materialize_lot_execution(session=session, lot_id="LOT-101")

    assert first.created_operations == 20
    assert first.created_attempts == 20
    assert second.created_operations == 0
    assert second.created_attempts == 0
    assert second.existing_operations == 20
    assert second.existing_attempts == 20
    assert session.scalar(select(func.count()).select_from(UnitOperationRow)) == 20
    assert session.scalar(select(func.count()).select_from(WorkAttemptRow)) == 20


def test_materializing_second_lot_adds_its_own_execution_instances() -> None:
    session = seeded_session()

    materialize_lot_execution(session=session, lot_id="LOT-101")
    result = materialize_lot_execution(session=session, lot_id="LOT-102")

    assert result.created_operations == 20
    assert result.created_attempts == 20
    assert session.scalar(select(func.count()).select_from(UnitOperationRow)) == 40
    assert session.scalar(select(func.count()).select_from(WorkAttemptRow)) == 40


def test_materialization_rejects_unknown_lot() -> None:
    session = seeded_session()

    try:
        materialize_lot_execution(session=session, lot_id="LOT-MISSING")
    except ValueError as exc:
        assert str(exc) == "unknown lot_id: LOT-MISSING"
    else:
        raise AssertionError("unknown LOT must be rejected")
