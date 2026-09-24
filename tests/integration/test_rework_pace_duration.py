from datetime import datetime
from zoneinfo import ZoneInfo

import pytest

from production_control.core.execution_state import WorkEventInput, WorkEventType
from production_control.core.pace_estimator import (
    PaceBasis,
    estimate_lot_process_work,
)
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
from production_control.persistence.rework_scheduler_adapter import (
    build_waiting_rework_schedule_inputs,
)

SEOUL = ZoneInfo("Asia/Seoul")

UNIT_ID = "LOT-101-U01"
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


def pace(
    *,
    standard: float,
    completed: list[float],
):
    return estimate_lot_process_work(
        planned_unit_count=4,
        standard_minutes_per_unit=standard,
        completed_active_minutes=completed,
        pace_min_samples=3,
    )


def test_tuning_rework_uses_current_actual_average_pace() -> None:
    session_factory = seeded_session_factory()
    fail_first_final_test(session_factory)
    session = session_factory()

    projection = project_unit_execution_order(
        session=session,
        unit_id=UNIT_ID,
    )
    tuning_pace = pace(
        standard=25,
        completed=[20, 30, 28],
    )
    items = build_waiting_rework_schedule_inputs(
        session=session,
        projection=projection,
        pace_by_process={"TUNING": tuning_pace},
    )

    assert tuning_pace.pace_basis is PaceBasis.ACTUAL_AVERAGE
    assert len(items) == 1
    item = items[0]
    assert item.operation.process_code == "TUNING"
    assert item.operation.duration_minutes == pytest.approx(26)
    assert item.operation.execution_seq == 6
    assert item.operation.release_at == dt(10, 30)
    assert {
        requirement.resource_code
        for requirement in item.operation.requirements
    } == {"WORKER_POOL", "TUNING_STATION"}
    session.close()


def test_tuning_rework_uses_standard_based_pace_before_sample_threshold() -> None:
    session_factory = seeded_session_factory()
    fail_first_final_test(session_factory)
    session = session_factory()

    projection = project_unit_execution_order(
        session=session,
        unit_id=UNIT_ID,
    )
    tuning_pace = pace(
        standard=25,
        completed=[20, 30],
    )
    items = build_waiting_rework_schedule_inputs(
        session=session,
        projection=projection,
        pace_by_process={"TUNING": tuning_pace},
    )

    assert tuning_pace.pace_basis is PaceBasis.STANDARD
    assert items[0].operation.duration_minutes == 25
    session.close()


def test_final_test_retest_uses_current_final_test_pace_and_resources() -> None:
    session_factory = seeded_session_factory()
    fail_first_final_test(session_factory)
    complete_tuning_rework(session_factory)
    session = session_factory()

    projection = project_unit_execution_order(
        session=session,
        unit_id=UNIT_ID,
    )
    final_test_pace = pace(
        standard=30,
        completed=[30, 33, 30],
    )
    items = build_waiting_rework_schedule_inputs(
        session=session,
        projection=projection,
        pace_by_process={"FINAL_TEST": final_test_pace},
    )

    assert len(items) == 1
    item = items[0]
    assert item.operation.process_code == "FINAL_TEST"
    assert item.operation.duration_minutes == pytest.approx(31)
    assert item.operation.execution_seq == 7
    assert item.operation.release_at == dt(11, 25)
    assert {
        requirement.resource_code
        for requirement in item.operation.requirements
    } == {"WORKER_POOL", "TEST_STATION"}
    session.close()


def test_rework_adapter_requires_current_pace_for_its_process() -> None:
    session_factory = seeded_session_factory()
    fail_first_final_test(session_factory)
    session = session_factory()

    projection = project_unit_execution_order(
        session=session,
        unit_id=UNIT_ID,
    )

    with pytest.raises(
        ValueError,
        match="missing current LOT x process Pace for rework process: TUNING",
    ):
        build_waiting_rework_schedule_inputs(
            session=session,
            projection=projection,
            pace_by_process={},
        )
    session.close()
