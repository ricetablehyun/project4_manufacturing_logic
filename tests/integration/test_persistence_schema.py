from datetime import datetime
from zoneinfo import ZoneInfo

import pytest
from sqlalchemy import inspect
from sqlalchemy.exc import IntegrityError

from production_control.persistence.database import (
    create_schema,
    create_session_factory,
    create_sqlite_engine,
)
from production_control.persistence.models import (
    LotRow,
    ProcessRow,
    ProductRow,
    RoutingRow,
    RoutingStepRow,
    SchedulePlanRow,
    UnitOperationRow,
    UnitRow,
    WorkAttemptRow,
    WorkEventRow,
)

SEOUL = ZoneInfo("Asia/Seoul")


def dt(hour: int) -> datetime:
    return datetime(2026, 10, 5, hour, tzinfo=SEOUL)


def seeded_session():
    engine = create_sqlite_engine()
    create_schema(engine)
    session = create_session_factory(engine)()

    session.add(ProductRow(product_id="P1", product_code="RF-MOCK-A", name="RF Mock A"))
    session.add(ProcessRow(process_id="PR-T", process_code="TUNING", name="Tuning", process_kind="INTERNAL"))
    session.add(RoutingRow(routing_id="R1", product_id="P1", version=1, active=True))
    session.add(
        RoutingStepRow(
            routing_step_id="RS4",
            routing_id="R1",
            process_id="PR-T",
            seq_no=4,
            duration_mode="UNIT_TIME",
            standard_minutes=25,
        )
    )
    session.add(
        LotRow(
            lot_id="L1",
            product_id="P1",
            lot_code="LOT-101",
            quantity=4,
            release_at=dt(9),
            due_at=dt(17),
            status="ACTIVE",
            created_at=dt(8),
        )
    )
    session.add(UnitRow(unit_id="U1", lot_id="L1", unit_code="U01", status="ACTIVE"))
    session.add(
        UnitOperationRow(
            unit_operation_id="OP1",
            unit_id="U1",
            routing_step_id="RS4",
            state="RUNNING",
            eligible_at=dt(9),
            current_attempt_no=1,
        )
    )
    session.add(
        WorkAttemptRow(
            attempt_id="A1",
            unit_operation_id="OP1",
            attempt_no=1,
            started_at=dt(10),
            active_minutes=0,
        )
    )
    session.commit()
    return engine, session


def test_schema_contains_confirmed_v1_tables() -> None:
    engine = create_sqlite_engine()
    create_schema(engine)

    assert set(inspect(engine).get_table_names()) == {
        "calendar_exception",
        "inspection_gate",
        "lot",
        "process",
        "product",
        "resource",
        "routing",
        "routing_step",
        "routing_step_resource",
        "schedule_plan",
        "schedule_task",
        "unit",
        "unit_operation",
        "work_attempt",
        "work_calendar",
        "work_event",
    }


def test_work_event_id_is_unique_for_idempotent_persistence() -> None:
    _, session = seeded_session()
    first = WorkEventRow(
        event_id="evt-001",
        attempt_id="A1",
        event_type="START",
        occurred_at=dt(10),
        received_at=dt(10),
    )
    session.add(first)
    session.commit()

    session.add(
        WorkEventRow(
            event_id="evt-001",
            attempt_id="A1",
            event_type="START",
            occurred_at=dt(10),
            received_at=dt(10),
        )
    )

    with pytest.raises(IntegrityError):
        session.commit()


def test_foreign_keys_reject_event_for_unknown_attempt() -> None:
    engine = create_sqlite_engine()
    create_schema(engine)
    session = create_session_factory(engine)()
    session.add(
        WorkEventRow(
            event_id="evt-missing",
            attempt_id="NO-SUCH-ATTEMPT",
            event_type="START",
            occurred_at=dt(10),
            received_at=dt(10),
        )
    )

    with pytest.raises(IntegrityError):
        session.commit()


def test_schedule_plan_can_preserve_parent_version_link() -> None:
    engine = create_sqlite_engine()
    create_schema(engine)
    session = create_session_factory(engine)()

    v1 = SchedulePlanRow(
        plan_id="PLAN-1",
        version=1,
        plan_kind="INITIAL",
        priority_rule="EDD",
        status="APPROVED",
        created_at=dt(9),
        approved_at=dt(9),
    )
    session.add(v1)
    session.commit()

    v2 = SchedulePlanRow(
        plan_id="PLAN-2",
        version=2,
        plan_kind="REPLAN",
        priority_rule="SLACK",
        status="APPROVED",
        parent_plan_id="PLAN-1",
        trigger_reason="URGENT_GATE_RISK",
        created_at=dt(11),
        approved_at=dt(11),
        late_lot_count=0,
        total_tardiness_minutes=0,
        overtime_minutes=60,
        change_count=2,
    )
    session.add(v2)
    session.commit()

    persisted = session.get(SchedulePlanRow, "PLAN-2")
    assert persisted is not None
    assert persisted.parent_plan_id == "PLAN-1"
    assert persisted.version == 2
    assert session.get(SchedulePlanRow, "PLAN-1") is not None


def test_sqlite_file_database_can_be_reopened(tmp_path) -> None:
    db_path = tmp_path / "production.db"
    engine = create_sqlite_engine(db_path)
    create_schema(engine)
    session = create_session_factory(engine)()
    session.add(ProductRow(product_id="P1", product_code="RF-MOCK-A", name="RF Mock A"))
    session.commit()
    session.close()
    engine.dispose()

    reopened = create_sqlite_engine(db_path)
    session = create_session_factory(reopened)()
    persisted = session.get(ProductRow, "P1")

    assert persisted is not None
    assert persisted.product_code == "RF-MOCK-A"
