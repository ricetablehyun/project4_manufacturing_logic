from datetime import datetime
from zoneinfo import ZoneInfo

from sqlalchemy import func, select

from production_control.core.execution_state import WorkEventInput, WorkEventType
from production_control.persistence.database import (
    create_schema,
    create_session_factory,
    create_sqlite_engine,
)
from production_control.persistence.execution_service import persist_work_event
from production_control.persistence.fixture_seed import seed_f02_fixture
from production_control.persistence.materialization import materialize_lot_execution
from production_control.persistence.models import UnitOperationRow, WorkAttemptRow

SEOUL = ZoneInfo("Asia/Seoul")

TUNING_OPERATION = "OP::LOT-101-U01::STEP-04-TUNING"
FINAL_TEST_OPERATION = "OP::LOT-101-U01::STEP-06-FINAL-TEST"


def dt(hour: int, minute: int = 0) -> datetime:
    return datetime(2026, 10, 5, hour, minute, tzinfo=SEOUL)


def seeded_session_factory():
    engine = create_sqlite_engine()
    create_schema(engine)
    session_factory = create_session_factory(engine)
    session = session_factory()
    seed_f02_fixture(session)
    materialize_lot_execution(session=session, lot_id="LOT-101")
    session.close()
    return session_factory


def apply_event(
    session_factory,
    *,
    operation_id: str,
    event_id: str,
    event_type: WorkEventType,
    occurred_at: datetime,
    reason: str | None = None,
):
    session = session_factory()
    try:
        return persist_work_event(
            session=session,
            unit_operation_id=operation_id,
            event=WorkEventInput(
                event_id=event_id,
                event_type=event_type,
                occurred_at=occurred_at,
                reason=reason,
            ),
            received_at=occurred_at,
        )
    finally:
        session.close()


def complete_normal_tuning(session_factory) -> None:
    apply_event(
        session_factory,
        operation_id=TUNING_OPERATION,
        event_id="T1-START",
        event_type=WorkEventType.START,
        occurred_at=dt(9),
    )
    apply_event(
        session_factory,
        operation_id=TUNING_OPERATION,
        event_id="T1-COMPLETE",
        event_type=WorkEventType.COMPLETE,
        occurred_at=dt(9, 25),
    )


def fail_first_final_test(session_factory):
    complete_normal_tuning(session_factory)
    apply_event(
        session_factory,
        operation_id=FINAL_TEST_OPERATION,
        event_id="F1-START",
        event_type=WorkEventType.START,
        occurred_at=dt(10),
    )
    return apply_event(
        session_factory,
        operation_id=FINAL_TEST_OPERATION,
        event_id="F1-FAIL",
        event_type=WorkEventType.FAIL,
        occurred_at=dt(10, 30),
        reason="temperature margin shortage",
    )


def complete_tuning_rework(session_factory) -> None:
    apply_event(
        session_factory,
        operation_id=TUNING_OPERATION,
        event_id="T2-START",
        event_type=WorkEventType.START,
        occurred_at=dt(11),
    )
    apply_event(
        session_factory,
        operation_id=TUNING_OPERATION,
        event_id="T2-COMPLETE",
        event_type=WorkEventType.COMPLETE,
        occurred_at=dt(11, 25),
    )


def test_final_test_fail_creates_only_tuning_rework_attempt() -> None:
    session_factory = seeded_session_factory()

    result = fail_first_final_test(session_factory)

    assert result.rework_trigger is not None

    session = session_factory()
    tuning = session.get(UnitOperationRow, TUNING_OPERATION)
    final_test = session.get(UnitOperationRow, FINAL_TEST_OPERATION)
    tuning_attempt = session.scalar(
        select(WorkAttemptRow).where(
            WorkAttemptRow.unit_operation_id == TUNING_OPERATION,
            WorkAttemptRow.attempt_no == 2,
        )
    )
    final_attempt_count = session.scalar(
        select(func.count())
        .select_from(WorkAttemptRow)
        .where(WorkAttemptRow.unit_operation_id == FINAL_TEST_OPERATION)
    )

    assert tuning is not None
    assert tuning.state == "WAITING"
    assert tuning.current_attempt_no == 2
    assert tuning.eligible_at == dt(10, 30)

    assert tuning_attempt is not None
    assert tuning_attempt.rework_role == "TUNING_REWORK"
    assert tuning_attempt.rework_source_ref == FINAL_TEST_OPERATION
    assert tuning_attempt.rework_event_ref == "F1-FAIL"
    assert tuning_attempt.rework_detail == "temperature margin shortage"

    assert final_test is not None
    assert final_test.state == "COMPLETED"
    assert final_test.current_attempt_no == 1
    assert final_attempt_count == 1
    session.close()


def test_tuning_rework_complete_then_creates_final_test_retest() -> None:
    session_factory = seeded_session_factory()
    fail_first_final_test(session_factory)

    complete_tuning_rework(session_factory)

    session = session_factory()
    final_test = session.get(UnitOperationRow, FINAL_TEST_OPERATION)
    retest = session.scalar(
        select(WorkAttemptRow).where(
            WorkAttemptRow.unit_operation_id == FINAL_TEST_OPERATION,
            WorkAttemptRow.attempt_no == 2,
        )
    )

    assert final_test is not None
    assert final_test.state == "WAITING"
    assert final_test.current_attempt_no == 2
    assert final_test.eligible_at == dt(11, 25)

    assert retest is not None
    assert retest.rework_role == "FINAL_TEST_RETEST"
    assert retest.rework_source_ref == FINAL_TEST_OPERATION
    assert retest.rework_event_ref == "F1-FAIL"
    assert retest.rework_detail == "temperature margin shortage"
    session.close()


def test_duplicate_fail_event_does_not_create_another_tuning_attempt() -> None:
    session_factory = seeded_session_factory()
    fail_first_final_test(session_factory)

    duplicate = apply_event(
        session_factory,
        operation_id=FINAL_TEST_OPERATION,
        event_id="F1-FAIL",
        event_type=WorkEventType.FAIL,
        occurred_at=dt(10, 30),
        reason="temperature margin shortage",
    )

    assert duplicate.duplicate

    session = session_factory()
    tuning_attempt_count = session.scalar(
        select(func.count())
        .select_from(WorkAttemptRow)
        .where(WorkAttemptRow.unit_operation_id == TUNING_OPERATION)
    )

    assert tuning_attempt_count == 2
    session.close()


def test_repeated_final_test_fail_stages_tuning_attempt_three() -> None:
    session_factory = seeded_session_factory()
    fail_first_final_test(session_factory)
    complete_tuning_rework(session_factory)

    apply_event(
        session_factory,
        operation_id=FINAL_TEST_OPERATION,
        event_id="F2-START",
        event_type=WorkEventType.START,
        occurred_at=dt(12),
    )
    apply_event(
        session_factory,
        operation_id=FINAL_TEST_OPERATION,
        event_id="F2-FAIL",
        event_type=WorkEventType.FAIL,
        occurred_at=dt(12, 30),
        reason="margin still unstable",
    )

    session = session_factory()
    tuning = session.get(UnitOperationRow, TUNING_OPERATION)
    third_attempt = session.scalar(
        select(WorkAttemptRow).where(
            WorkAttemptRow.unit_operation_id == TUNING_OPERATION,
            WorkAttemptRow.attempt_no == 3,
        )
    )

    assert tuning is not None
    assert tuning.current_attempt_no == 3
    assert tuning.state == "WAITING"
    assert third_attempt is not None
    assert third_attempt.rework_role == "TUNING_REWORK"
    assert third_attempt.rework_event_ref == "F2-FAIL"
    assert third_attempt.rework_detail == "margin still unstable"
    session.close()
