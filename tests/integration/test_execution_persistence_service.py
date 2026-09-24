from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

import pytest
from sqlalchemy import func, select

from production_control.core.execution_state import WorkEventInput, WorkEventType
from production_control.persistence.database import (
    create_schema,
    create_session_factory,
    create_sqlite_engine,
)
from production_control.persistence.execution_service import persist_work_event
from production_control.persistence.models import (
    LotRow,
    ProcessRow,
    ProductRow,
    RoutingRow,
    RoutingStepRow,
    UnitOperationRow,
    UnitRow,
    WorkAttemptRow,
    WorkEventRow,
)

SEOUL = ZoneInfo("Asia/Seoul")


def dt(hour: int, minute: int = 0) -> datetime:
    return datetime(2026, 10, 5, hour, minute, tzinfo=SEOUL)


def seed_execution_database(*, process_code: str = "TUNING"):
    engine = create_sqlite_engine()
    create_schema(engine)
    session_factory = create_session_factory(engine)
    session = session_factory()

    session.add(
        ProductRow(
            product_id="P1",
            product_code="RF-MOCK-A",
            name="RF Mock A",
        )
    )
    session.add(
        ProcessRow(
            process_id="PR1",
            process_code=process_code,
            name=process_code,
            process_kind="INTERNAL",
        )
    )
    session.flush()

    session.add(
        RoutingRow(
            routing_id="R1",
            product_id="P1",
            version=1,
            active=True,
        )
    )
    session.flush()

    session.add(
        RoutingStepRow(
            routing_step_id="RS1",
            routing_id="R1",
            process_id="PR1",
            seq_no=1,
            duration_mode="UNIT_TIME",
            standard_minutes=25,
        )
    )
    session.add(
        LotRow(
            lot_id="L1",
            product_id="P1",
            lot_code="LOT-101",
            quantity=1,
            release_at=dt(9),
            due_at=dt(17),
            status="ACTIVE",
            created_at=dt(8),
        )
    )
    session.flush()

    session.add(
        UnitRow(
            unit_id="U1",
            lot_id="L1",
            unit_code="U01",
            status="ACTIVE",
        )
    )
    session.flush()

    session.add(
        UnitOperationRow(
            unit_operation_id="OP1",
            unit_id="U1",
            routing_step_id="RS1",
            state="WAITING",
            eligible_at=dt(9),
            current_attempt_no=1,
        )
    )
    session.flush()

    session.add(
        WorkAttemptRow(
            attempt_id="A1",
            unit_operation_id="OP1",
            attempt_no=1,
            active_minutes=0,
        )
    )
    session.commit()
    session.close()
    return engine, session_factory


def apply_event(
    session_factory,
    *,
    event_id: str,
    event_type: WorkEventType,
    occurred_at: datetime,
    reason: str | None = None,
):
    session = session_factory()
    try:
        return persist_work_event(
            session=session,
            unit_operation_id="OP1",
            event=WorkEventInput(
                event_id=event_id,
                event_type=event_type,
                occurred_at=occurred_at,
                reason=reason,
            ),
            received_at=occurred_at,
            station_code="STATION-1",
            worker_code="WORKER-A",
        )
    finally:
        session.close()


def test_start_persists_state_and_timezone_across_fresh_session() -> None:
    _, session_factory = seed_execution_database()

    result = apply_event(
        session_factory,
        event_id="E1",
        event_type=WorkEventType.START,
        occurred_at=dt(10),
    )

    assert not result.duplicate
    assert result.snapshot.state.value == "RUNNING"

    session = session_factory()
    operation = session.get(UnitOperationRow, "OP1")
    attempt = session.get(WorkAttemptRow, "A1")
    persisted_event = session.get(WorkEventRow, "E1")

    assert operation is not None
    assert operation.state == "RUNNING"
    assert attempt is not None
    assert attempt.started_at == dt(10)
    assert attempt.started_at.utcoffset() == timedelta(hours=9)
    assert persisted_event is not None
    assert persisted_event.occurred_at.utcoffset() == timedelta(hours=9)
    session.close()


def test_hold_resume_complete_accumulates_only_active_minutes() -> None:
    _, session_factory = seed_execution_database()

    apply_event(
        session_factory,
        event_id="E1",
        event_type=WorkEventType.START,
        occurred_at=dt(10),
    )
    apply_event(
        session_factory,
        event_id="E2",
        event_type=WorkEventType.HOLD,
        occurred_at=dt(10, 35),
        reason="TUNING_UNSTABLE",
    )
    apply_event(
        session_factory,
        event_id="E3",
        event_type=WorkEventType.RESUME,
        occurred_at=dt(11, 30),
    )
    result = apply_event(
        session_factory,
        event_id="E4",
        event_type=WorkEventType.COMPLETE,
        occurred_at=dt(12),
    )

    assert result.snapshot.active_minutes == 65
    assert result.snapshot.attempt_no == 1

    session = session_factory()
    operation = session.get(UnitOperationRow, "OP1")
    attempt = session.get(WorkAttemptRow, "A1")
    event_count = session.scalar(select(func.count()).select_from(WorkEventRow))

    assert operation is not None
    assert operation.state == "COMPLETED"
    assert attempt is not None
    assert attempt.active_minutes == 65
    assert attempt.ended_at == dt(12)
    assert event_count == 4
    session.close()


def test_duplicate_event_id_returns_duplicate_without_second_row() -> None:
    _, session_factory = seed_execution_database()

    first = apply_event(
        session_factory,
        event_id="E1",
        event_type=WorkEventType.START,
        occurred_at=dt(10),
    )
    duplicate = apply_event(
        session_factory,
        event_id="E1",
        event_type=WorkEventType.START,
        occurred_at=dt(10),
    )

    assert not first.duplicate
    assert duplicate.duplicate

    session = session_factory()
    event_count = session.scalar(select(func.count()).select_from(WorkEventRow))
    attempt = session.get(WorkAttemptRow, "A1")

    assert event_count == 1
    assert attempt is not None
    assert attempt.active_minutes == 0
    session.close()


def test_final_test_fail_persists_result_and_returns_rework_signal() -> None:
    _, session_factory = seed_execution_database(process_code="FINAL_TEST")

    apply_event(
        session_factory,
        event_id="E1",
        event_type=WorkEventType.START,
        occurred_at=dt(13),
    )
    result = apply_event(
        session_factory,
        event_id="E2",
        event_type=WorkEventType.FAIL,
        occurred_at=dt(13, 30),
        reason="temperature margin shortage",
    )

    assert result.rework_trigger is not None
    assert result.rework_trigger.source_operation_id == "OP1"
    assert result.rework_trigger.event_id == "E2"
    assert result.rework_trigger.reason == "temperature margin shortage"

    session = session_factory()
    operation = session.get(UnitOperationRow, "OP1")
    attempt = session.get(WorkAttemptRow, "A1")
    fail_event = session.get(WorkEventRow, "E2")

    assert operation is not None
    assert operation.state == "COMPLETED"
    assert attempt is not None
    assert attempt.result == "FAIL"
    assert attempt.active_minutes == 30
    assert fail_event is not None
    assert fail_event.reason == "temperature margin shortage"
    session.close()


def test_invalid_event_does_not_persist_partial_changes() -> None:
    _, session_factory = seed_execution_database()

    with pytest.raises(ValueError):
        apply_event(
            session_factory,
            event_id="E1",
            event_type=WorkEventType.HOLD,
            occurred_at=dt(10),
            reason="cannot hold before start",
        )

    session = session_factory()
    operation = session.get(UnitOperationRow, "OP1")
    event_count = session.scalar(select(func.count()).select_from(WorkEventRow))

    assert operation is not None
    assert operation.state == "WAITING"
    assert event_count == 0
    session.close()
