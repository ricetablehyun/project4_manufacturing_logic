from datetime import datetime
from zoneinfo import ZoneInfo

import pytest

from production_control.core.event_scheduler import schedule_operations_event_driven
from production_control.core.execution_state import WorkEventInput, WorkEventType
from production_control.core.pace_estimator import estimate_lot_process_work
from production_control.core.pace_scheduler_adapter import ForecastReadiness
from production_control.core.priority_rules import LotPriorityInput, PriorityRule
from production_control.persistence.database import (
    create_schema,
    create_session_factory,
    create_sqlite_engine,
)
from production_control.persistence.execution_service import persist_work_event
from production_control.persistence.fixture_seed import seed_f02_fixture
from production_control.persistence.forecast_input_bundle import (
    build_internal_lot_forecast_inputs,
)
from production_control.persistence.mappers import (
    load_active_resources,
    load_work_calendar,
)
from production_control.persistence.materialization import materialize_lot_execution

SEOUL = ZoneInfo("Asia/Seoul")

LOT_ID = "LOT-101"
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
    materialize_lot_execution(session=session, lot_id=LOT_ID)
    session.close()
    return session_factory


def standard_forecasts(
    *,
    tuning_completed: list[float] | None = None,
    final_test_completed: list[float] | None = None,
):
    specs = {
        "TAPING": (10, []),
        "GENERAL_ASSEMBLY": (10, []),
        "TUNING": (25, tuning_completed or []),
        "FINISH_ASSEMBLY": (10, []),
        "FINAL_TEST": (30, final_test_completed or []),
    }
    return {
        process_code: estimate_lot_process_work(
            planned_unit_count=4,
            standard_minutes_per_unit=standard,
            completed_active_minutes=completed,
            pace_min_samples=3,
        )
        for process_code, (standard, completed) in specs.items()
    }


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
        occurred_at=dt(9, 20),
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


def test_fresh_lot_builds_all_internal_normal_attempts() -> None:
    session_factory = seeded_session_factory()
    session = session_factory()

    bundle = build_internal_lot_forecast_inputs(
        session=session,
        lot_id=LOT_ID,
        pace_by_process=standard_forecasts(),
    )

    assert bundle.readiness is ForecastReadiness.READY
    assert len(bundle.items) == 20
    assert bundle.waiting_operation_ids == ()

    u01 = [
        item
        for item in bundle.items
        if item.operation.unit_id == UNIT_ID
    ]
    assert [
        (
            item.operation.process_code,
            item.operation.step_seq,
            item.operation.execution_seq,
        )
        for item in u01
    ] == [
        ("TAPING", 1, 1),
        ("GENERAL_ASSEMBLY", 3, 2),
        ("TUNING", 4, 3),
        ("FINISH_ASSEMBLY", 5, 4),
        ("FINAL_TEST", 6, 5),
    ]
    session.close()


def test_normal_attempt_uses_attempt_id_and_persisted_resources() -> None:
    session_factory = seeded_session_factory()
    session = session_factory()

    bundle = build_internal_lot_forecast_inputs(
        session=session,
        lot_id=LOT_ID,
        pace_by_process=standard_forecasts(),
    )
    tuning = next(
        item
        for item in bundle.items
        if (
            item.operation.unit_id == UNIT_ID
            and item.operation.process_code == "TUNING"
        )
    )

    assert tuning.operation.operation_id == (
        "ATTEMPT::OP::LOT-101-U01::STEP-04-TUNING::1"
    )
    assert tuning.operation.duration_minutes == 25
    assert {
        requirement.resource_code
        for requirement in tuning.operation.requirements
    } == {"WORKER_POOL", "TUNING_STATION"}
    session.close()


def test_normal_and_rework_tuning_share_same_lot_process_pace_without_double_count() -> None:
    session_factory = seeded_session_factory()
    fail_first_final_test(session_factory)
    session = session_factory()

    forecasts = standard_forecasts(
        tuning_completed=[20],
        final_test_completed=[30],
    )
    bundle = build_internal_lot_forecast_inputs(
        session=session,
        lot_id=LOT_ID,
        pace_by_process=forecasts,
    )

    tuning_items = [
        item
        for item in bundle.items
        if item.operation.process_code == "TUNING"
    ]
    normal = [
        item
        for item in tuning_items
        if item.operation.operation_id.endswith("::1")
    ]
    rework = [
        item
        for item in tuning_items
        if item.operation.operation_id.endswith("::2")
    ]

    assert len(normal) == 3
    assert len(rework) == 1
    assert [
        item.operation.duration_minutes for item in normal
    ] == [
        pytest.approx(80 / 3),
        pytest.approx(80 / 3),
        pytest.approx(80 / 3),
    ]
    assert rework[0].operation.duration_minutes == 25
    assert rework[0].operation.execution_seq == 6
    assert sum(
        item.operation.duration_minutes for item in tuning_items
    ) == pytest.approx(105)
    session.close()


def test_bundle_rejects_missing_pace_for_current_normal_process() -> None:
    session_factory = seeded_session_factory()
    session = session_factory()
    forecasts = standard_forecasts()
    forecasts.pop("TAPING")

    with pytest.raises(
        ValueError,
        match="missing current LOT x process Pace for normal process: TAPING",
    ):
        build_internal_lot_forecast_inputs(
            session=session,
            lot_id=LOT_ID,
            pace_by_process=forecasts,
        )
    session.close()


def test_persisted_bundle_flows_into_internal_event_scheduler() -> None:
    session_factory = seeded_session_factory()
    session = session_factory()

    bundle = build_internal_lot_forecast_inputs(
        session=session,
        lot_id=LOT_ID,
        pace_by_process=standard_forecasts(),
    )
    schedule = schedule_operations_event_driven(
        items=bundle.items,
        rule=PriorityRule.EDD,
        static_lot_priorities=(
            LotPriorityInput(
                lot_id=LOT_ID,
                release_at=dt(9),
                deadline=dt(15, 30),
                remaining_work_minutes=340,
                time_until_deadline_minutes=390,
            ),
        ),
        resources=load_active_resources(session),
        calendar=load_work_calendar(session, "CALENDAR-NORMAL"),
        start_time=dt(9),
    )

    assert len(schedule.operations) == 20
    assert {
        operation.operation_id
        for operation in schedule.operations
    } == {
        item.operation.operation_id
        for item in bundle.items
    }
    assert all(
        operation.execution_seq is not None
        for operation in schedule.operations
    )
    session.close()
