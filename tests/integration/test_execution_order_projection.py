from datetime import datetime
from zoneinfo import ZoneInfo

from production_control.core.execution_state import WorkEventInput, WorkEventType
from production_control.persistence.database import (
    create_schema,
    create_session_factory,
    create_sqlite_engine,
)
from production_control.persistence.execution_projection import (
    project_unit_execution_order,
)
from production_control.persistence.execution_service import persist_work_event
from production_control.persistence.fixture_seed import seed_f02_fixture
from production_control.persistence.materialization import materialize_lot_execution
from production_control.persistence.models import (
    ProcessRow,
    RoutingStepRow,
)

SEOUL = ZoneInfo("Asia/Seoul")

UNIT_ID = "LOT-101-U01"
TUNING_OPERATION = "OP::LOT-101-U01::STEP-04-TUNING"
FINAL_TEST_OPERATION = "OP::LOT-101-U01::STEP-06-FINAL-TEST"
SHIPPING_OPERATION = "OP::LOT-101-U01::STEP-07-SHIPPING"


def dt(hour: int, minute: int = 0) -> datetime:
    return datetime(2026, 10, 5, hour, minute, tzinfo=SEOUL)


def seeded_session_factory(*, with_downstream: bool = False):
    engine = create_sqlite_engine()
    create_schema(engine)
    session_factory = create_session_factory(engine)
    session = session_factory()
    seed_f02_fixture(session)

    if with_downstream:
        session.add(
            ProcessRow(
                process_id="PROCESS-SHIPPING",
                process_code="SHIPPING",
                name="Shipping",
                process_kind="INTERNAL",
            )
        )
        session.flush()
        session.add(
            RoutingStepRow(
                routing_step_id="STEP-07-SHIPPING",
                routing_id="ROUTING-RF-MOCK-A-V1",
                process_id="PROCESS-SHIPPING",
                seq_no=7,
                duration_mode="UNIT_TIME",
                standard_minutes=10,
            )
        )
        session.commit()

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
) -> None:
    session = session_factory()
    try:
        persist_work_event(
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


def fail_first_final_test(session_factory) -> None:
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
    apply_event(
        session_factory,
        operation_id=FINAL_TEST_OPERATION,
        event_id="F1-START",
        event_type=WorkEventType.START,
        occurred_at=dt(10),
    )
    apply_event(
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


def test_normal_projection_keeps_routing_identity_but_uses_dense_execution_order() -> None:
    session_factory = seeded_session_factory()
    session = session_factory()

    projection = project_unit_execution_order(
        session=session,
        unit_id=UNIT_ID,
    )

    assert [
        (attempt.step_seq, attempt.execution_seq)
        for attempt in projection.attempts
    ] == [
        (1, 1),
        (3, 2),
        (4, 3),
        (5, 4),
        (6, 5),
    ]
    session.close()


def test_final_test_fail_projects_rework_after_source_despite_lower_step_seq() -> None:
    session_factory = seeded_session_factory()
    fail_first_final_test(session_factory)
    session = session_factory()

    projection = project_unit_execution_order(
        session=session,
        unit_id=UNIT_ID,
    )
    ordered = [
        (
            attempt.process_code,
            attempt.attempt_no,
            attempt.step_seq,
            attempt.execution_seq,
        )
        for attempt in projection.attempts
    ]

    assert ordered[-2:] == [
        ("FINAL_TEST", 1, 6, 5),
        ("TUNING", 2, 4, 6),
    ]
    session.close()


def test_unresolved_rework_blocks_normal_downstream_operation() -> None:
    session_factory = seeded_session_factory(with_downstream=True)
    fail_first_final_test(session_factory)
    session = session_factory()

    projection = project_unit_execution_order(
        session=session,
        unit_id=UNIT_ID,
    )
    shipping = next(
        attempt
        for attempt in projection.attempts
        if attempt.unit_operation_id == SHIPPING_OPERATION
    )

    assert shipping.step_seq == 7
    assert shipping.scheduler_blocked
    assert SHIPPING_OPERATION not in {
        attempt.unit_operation_id
        for attempt in projection.scheduler_current_attempts
    }
    session.close()


def test_retest_projection_unblocks_downstream_and_avoids_sequence_collision() -> None:
    session_factory = seeded_session_factory(with_downstream=True)
    fail_first_final_test(session_factory)
    complete_tuning_rework(session_factory)
    session = session_factory()

    projection = project_unit_execution_order(
        session=session,
        unit_id=UNIT_ID,
    )
    relevant = [
        attempt
        for attempt in projection.attempts
        if (
            attempt.unit_operation_id
            in {TUNING_OPERATION, FINAL_TEST_OPERATION, SHIPPING_OPERATION}
        )
    ]
    by_key = {
        (attempt.unit_operation_id, attempt.attempt_no): attempt
        for attempt in relevant
    }

    final_one = by_key[(FINAL_TEST_OPERATION, 1)]
    tuning_two = by_key[(TUNING_OPERATION, 2)]
    final_two = by_key[(FINAL_TEST_OPERATION, 2)]
    shipping = by_key[(SHIPPING_OPERATION, 1)]

    assert (
        final_one.execution_seq
        < tuning_two.execution_seq
        < final_two.execution_seq
        < shipping.execution_seq
    )
    assert len({
        attempt.execution_seq for attempt in projection.attempts
    }) == len(projection.attempts)
    assert not shipping.scheduler_blocked
    session.close()


def test_repeated_fail_appends_next_rework_cycle_after_retest() -> None:
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
    projection = project_unit_execution_order(
        session=session,
        unit_id=UNIT_ID,
    )
    relevant = [
        (
            attempt.process_code,
            attempt.attempt_no,
            attempt.execution_seq,
        )
        for attempt in projection.attempts
        if attempt.process_code in {"TUNING", "FINAL_TEST"}
    ]

    assert relevant == [
        ("TUNING", 1, 3),
        ("FINAL_TEST", 1, 5),
        ("TUNING", 2, 6),
        ("FINAL_TEST", 2, 7),
        ("TUNING", 3, 8),
    ]
    session.close()
