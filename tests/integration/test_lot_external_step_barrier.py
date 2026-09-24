from datetime import datetime
from zoneinfo import ZoneInfo

import pytest

from production_control.core.event_scheduler import schedule_operations_event_driven
from production_control.core.pace_estimator import estimate_lot_process_work
from production_control.core.pace_scheduler_adapter import ForecastReadiness
from production_control.core.priority_rules import LotPriorityInput, PriorityRule
from production_control.persistence.database import (
    create_schema,
    create_session_factory,
    create_sqlite_engine,
)
from production_control.persistence.external_step_barrier import (
    build_full_lot_forecast_inputs,
    load_lot_external_barriers,
    save_lot_external_step_state,
)
from production_control.persistence.fixture_seed import seed_f02_fixture
from production_control.persistence.mappers import (
    load_active_resources,
    load_work_calendar,
)
from production_control.persistence.materialization import materialize_lot_execution

SEOUL = ZoneInfo("Asia/Seoul")

LOT_ID = "LOT-101"
EXTERNAL_STEP_ID = "STEP-02-EXTERNAL-FEED-BONDING"


def dt(day: int, hour: int, minute: int = 0) -> datetime:
    return datetime(2026, 10, day, hour, minute, tzinfo=SEOUL)


def seeded_session_factory():
    engine = create_sqlite_engine()
    create_schema(engine)
    session_factory = create_session_factory(engine)
    session = session_factory()
    seed_f02_fixture(session)
    materialize_lot_execution(session=session, lot_id=LOT_ID)
    session.close()
    return session_factory


def standard_forecasts():
    specs = {
        "TAPING": 10,
        "GENERAL_ASSEMBLY": 10,
        "TUNING": 25,
        "FINISH_ASSEMBLY": 10,
        "FINAL_TEST": 30,
    }
    return {
        process_code: estimate_lot_process_work(
            planned_unit_count=4,
            standard_minutes_per_unit=standard,
            completed_active_minutes=[],
            pace_min_samples=3,
        )
        for process_code, standard in specs.items()
    }


def save_expected(
    session,
    *,
    expected_finish_at: datetime,
    actual_finish_at: datetime | None = None,
):
    return save_lot_external_step_state(
        session=session,
        lot_id=LOT_ID,
        routing_step_id=EXTERNAL_STEP_ID,
        expected_finish_at=expected_finish_at,
        actual_finish_at=actual_finish_at,
        status="EXPECTED" if actual_finish_at is None else "COMPLETED",
        updated_at=dt(5, 9),
    )


def test_missing_external_finish_makes_full_forecast_wait() -> None:
    session_factory = seeded_session_factory()
    session = session_factory()

    bundle = build_full_lot_forecast_inputs(
        session=session,
        lot_id=LOT_ID,
        pace_by_process=standard_forecasts(),
    )

    assert bundle.readiness is ForecastReadiness.WAIT
    assert bundle.items == ()
    assert bundle.missing_external_step_ids == (EXTERNAL_STEP_ID,)
    assert bundle.external_barriers == ()
    session.close()


def test_expected_finish_persists_as_lot_external_barrier() -> None:
    session_factory = seeded_session_factory()
    session = session_factory()
    save_expected(
        session,
        expected_finish_at=dt(5, 11),
    )

    barriers, missing = load_lot_external_barriers(
        session=session,
        lot_id=LOT_ID,
    )

    assert missing == ()
    assert len(barriers) == 1
    barrier = barriers[0]
    assert barrier.routing_step_id == EXTERNAL_STEP_ID
    assert barrier.process_code == "EXTERNAL_FEED_BONDING"
    assert barrier.step_seq == 2
    assert barrier.finish_at == dt(5, 11)
    assert barrier.finish_basis == "EXPECTED"
    session.close()


def test_actual_finish_overrides_previous_expected_finish() -> None:
    session_factory = seeded_session_factory()
    session = session_factory()
    save_expected(
        session,
        expected_finish_at=dt(5, 11),
        actual_finish_at=dt(5, 12),
    )

    barriers, missing = load_lot_external_barriers(
        session=session,
        lot_id=LOT_ID,
    )

    assert missing == ()
    assert barriers[0].finish_at == dt(5, 12)
    assert barriers[0].finish_basis == "ACTUAL"
    session.close()


def test_external_barrier_delays_only_downstream_internal_work() -> None:
    session_factory = seeded_session_factory()
    session = session_factory()
    save_expected(
        session,
        expected_finish_at=dt(5, 11),
    )

    bundle = build_full_lot_forecast_inputs(
        session=session,
        lot_id=LOT_ID,
        pace_by_process=standard_forecasts(),
    )

    assert bundle.readiness is ForecastReadiness.READY
    taping = [
        item
        for item in bundle.items
        if item.operation.process_code == "TAPING"
    ]
    downstream = [
        item
        for item in bundle.items
        if item.operation.step_seq > 2
    ]

    assert {item.operation.release_at for item in taping} == {dt(5, 9)}
    assert all(
        item.operation.release_at >= dt(5, 11)
        for item in downstream
    )
    session.close()


def test_full_f02_internal_schedule_respects_external_finish_barrier() -> None:
    session_factory = seeded_session_factory()
    session = session_factory()
    save_expected(
        session,
        expected_finish_at=dt(5, 11),
    )

    bundle = build_full_lot_forecast_inputs(
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
                release_at=dt(5, 9),
                deadline=dt(5, 15, 30),
                remaining_work_minutes=340,
                time_until_deadline_minutes=390,
            ),
        ),
        resources=load_active_resources(session),
        calendar=load_work_calendar(session, "CALENDAR-NORMAL"),
        start_time=dt(5, 9),
    )

    general_assembly = [
        operation
        for operation in schedule.operations
        if operation.process_code == "GENERAL_ASSEMBLY"
    ]

    assert len(schedule.operations) == 20
    assert general_assembly
    assert min(operation.start for operation in general_assembly) >= dt(5, 11)
    session.close()


def test_external_state_rejects_internal_unit_time_step() -> None:
    session_factory = seeded_session_factory()
    session = session_factory()

    with pytest.raises(
        ValueError,
        match="LotExternalStep requires LOT_LEAD_TIME RoutingStep",
    ):
        save_lot_external_step_state(
            session=session,
            lot_id=LOT_ID,
            routing_step_id="STEP-04-TUNING",
            expected_finish_at=dt(5, 11),
            actual_finish_at=None,
            status="EXPECTED",
            updated_at=dt(5, 9),
        )
    session.close()
