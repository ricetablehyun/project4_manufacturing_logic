from sqlalchemy import func, select

from production_control.persistence.database import (
    create_schema,
    create_session_factory,
    create_sqlite_engine,
)
from production_control.persistence.fixture_seed import seed_f02_fixture
from production_control.persistence.mappers import (
    load_active_resources,
    load_work_calendar,
)
from production_control.persistence.models import (
    InspectionGateRow,
    LotRow,
    ProcessRow,
    ResourceRow,
    RoutingStepResourceRow,
    RoutingStepRow,
    UnitRow,
)


def seeded_session():
    engine = create_sqlite_engine()
    create_schema(engine)
    session = create_session_factory(engine)()
    seed_f02_fixture(session)
    return session


def test_f02_seed_persists_exact_master_counts() -> None:
    session = seeded_session()

    assert session.scalar(select(func.count()).select_from(ProcessRow)) == 6
    assert session.scalar(select(func.count()).select_from(ResourceRow)) == 3
    assert session.scalar(select(func.count()).select_from(RoutingStepRow)) == 6
    assert (
        session.scalar(select(func.count()).select_from(RoutingStepResourceRow))
        == 7
    )


def test_f02_seed_persists_two_four_unit_lots() -> None:
    session = seeded_session()

    lots = session.scalars(select(LotRow).order_by(LotRow.lot_code)).all()
    assert [(lot.lot_code, lot.quantity) for lot in lots] == [
        ("LOT-101", 4),
        ("LOT-102", 4),
    ]

    units = session.scalars(select(UnitRow).order_by(UnitRow.unit_id)).all()
    assert len(units) == 8
    assert {unit.unit_code for unit in units} == {"U01", "U02", "U03", "U04"}


def test_f02_seed_keeps_unknown_external_lead_time_null() -> None:
    session = seeded_session()

    external = session.get(RoutingStepRow, "STEP-02-EXTERNAL-FEED-BONDING")
    assert external is not None
    assert external.duration_mode == "LOT_LEAD_TIME"
    assert external.external_lead_minutes is None


def test_f02_seed_persists_confirmed_process_times_and_buffer() -> None:
    session = seeded_session()

    expected = {
        "STEP-01-TAPING": (10, None),
        "STEP-03-GENERAL-ASSEMBLY": (10, None),
        "STEP-04-TUNING": (25, None),
        "STEP-05-FINISH-ASSEMBLY": (10, 2),
        "STEP-06-FINAL-TEST": (30, None),
    }

    for step_id, (minutes, buffer_k) in expected.items():
        step = session.get(RoutingStepRow, step_id)
        assert step is not None
        assert step.standard_minutes == minutes
        assert step.release_buffer_k == buffer_k


def test_f02_seed_persists_gate_dates_and_final_test_dependency() -> None:
    session = seeded_session()

    gate_101 = session.get(InspectionGateRow, "GATE-LOT-101-SHIPPING-INSPECTION")
    gate_102 = session.get(InspectionGateRow, "GATE-LOT-102-SHIPPING-INSPECTION")

    assert gate_101 is not None
    assert gate_102 is not None
    assert gate_101.required_after_step_id == "STEP-06-FINAL-TEST"
    assert gate_102.required_after_step_id == "STEP-06-FINAL-TEST"
    assert (gate_101.planned_at.month, gate_101.planned_at.day) == (10, 5)
    assert (gate_101.planned_at.hour, gate_101.planned_at.minute) == (15, 30)
    assert (gate_102.planned_at.month, gate_102.planned_at.day) == (10, 6)
    assert (gate_102.planned_at.hour, gate_102.planned_at.minute) == (11, 0)


def test_persisted_resources_map_back_to_scheduler_resources() -> None:
    session = seeded_session()

    resources = load_active_resources(session)

    assert resources["WORKER_POOL"].capacity == 2
    assert resources["TUNING_STATION"].capacity == 1
    assert resources["TEST_STATION"].capacity == 1


def test_persisted_calendar_maps_back_to_core_calendar() -> None:
    session = seeded_session()

    calendar = load_work_calendar(session, "CALENDAR-NORMAL")

    assert calendar.timezone == "Asia/Seoul"
    assert calendar.work_start.hour == 9
    assert calendar.work_end.hour == 17
    assert calendar.active_weekdays == frozenset({0, 1, 2, 3, 4})
