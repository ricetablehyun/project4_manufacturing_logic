from datetime import datetime
from zoneinfo import ZoneInfo

import pytest

from production_control.core.dispatch_builder import OperationDispatchInput
from production_control.core.event_scheduler import (
    EventDispatchInput,
    schedule_operations_event_driven,
)
from production_control.core.finite_scheduler import OperationSpec
from production_control.core.priority_rules import PriorityRule
from production_control.core.resource_engine import Resource
from production_control.core.slot_engine import ResourceRequirement
from production_control.domain.enums import OperationState
from production_control.persistence.database import (
    create_schema,
    create_session_factory,
    create_sqlite_engine,
)
from production_control.persistence.fixture_seed import seed_f02_fixture
from production_control.persistence.models import SchedulePlanRow, ScheduleTaskRow
from production_control.persistence.plan_dispatch import (
    build_plan_ready_dispatch_provider,
    load_plan_task_priorities,
)
from production_control.core.calendar_engine import WorkCalendar

SEOUL = ZoneInfo("Asia/Seoul")
PLAN_ID = "PLAN-APPROVED-1"


def dt(hour: int, minute: int = 0) -> datetime:
    return datetime(2026, 10, 5, hour, minute, tzinfo=SEOUL)


def seeded_session():
    engine = create_sqlite_engine()
    create_schema(engine)
    session_factory = create_session_factory(engine)
    session = session_factory()
    seed_f02_fixture(session)
    return session


def tuning_item(
    operation_id: str,
    lot_id: str,
    unit_id: str,
    *,
    state: OperationState = OperationState.WAITING,
    eligible_at: datetime | None = None,
) -> EventDispatchInput:
    eligible = eligible_at or dt(9)
    return EventDispatchInput(
        operation=OperationSpec(
            operation_id=operation_id,
            lot_id=lot_id,
            unit_id=unit_id,
            step_seq=4,
            process_code="TUNING",
            duration_minutes=25,
            requirements=(ResourceRequirement("TUNING_STATION"),),
            release_at=dt(9),
        ),
        dispatch=OperationDispatchInput(
            operation_id=operation_id,
            lot_id=lot_id,
            unit_id=unit_id,
            state=state,
            eligible_at=eligible,
        ),
    )


def add_plan(session, *, include_lot_102: bool = True) -> None:
    session.add(
        SchedulePlanRow(
            plan_id=PLAN_ID,
            version=1,
            plan_kind="BASELINE",
            priority_rule="EDD",
            status="APPROVED",
            parent_plan_id=None,
            trigger_reason=None,
            created_at=dt(8),
            approved_at=dt(8, 30),
            late_lot_count=0,
            total_tardiness_minutes=0,
            overtime_minutes=0,
            change_count=0,
        )
    )
    session.add(
        ScheduleTaskRow(
            schedule_task_id="TASK-LOT-101-TUNING",
            plan_id=PLAN_ID,
            lot_id="LOT-101",
            routing_step_id="STEP-04-TUNING",
            target_start=dt(9),
            target_end=dt(11),
            target_qty=4,
            priority_rank=2,
        )
    )
    if include_lot_102:
        session.add(
            ScheduleTaskRow(
                schedule_task_id="TASK-LOT-102-TUNING",
                plan_id=PLAN_ID,
                lot_id="LOT-102",
                routing_step_id="STEP-04-TUNING",
                target_start=dt(9),
                target_end=dt(11),
                target_qty=4,
                priority_rank=1,
            )
        )
    session.commit()


def test_load_plan_task_priorities_uses_persisted_rank_order() -> None:
    session = seeded_session()
    add_plan(session)

    priorities = load_plan_task_priorities(session=session, plan_id=PLAN_ID)

    assert [priority.lot_id for priority in priorities] == ["LOT-102", "LOT-101"]
    assert [priority.priority_rank for priority in priorities] == [1, 2]
    session.close()


def test_provider_orders_ready_operations_by_schedule_task_priority() -> None:
    session = seeded_session()
    add_plan(session)
    items = (
        tuning_item("OP-101", "LOT-101", "LOT-101-U01"),
        tuning_item("OP-102", "LOT-102", "LOT-102-U01"),
    )

    provider = build_plan_ready_dispatch_provider(
        session=session,
        plan_id=PLAN_ID,
        items=items,
    )

    assert provider(dt(9), items) == ("OP-102", "OP-101")
    session.close()


def test_event_scheduler_follows_approved_plan_rank_over_rule_path() -> None:
    session = seeded_session()
    add_plan(session)
    items = (
        tuning_item("OP-101", "LOT-101", "LOT-101-U01"),
        tuning_item("OP-102", "LOT-102", "LOT-102-U01"),
    )
    provider = build_plan_ready_dispatch_provider(
        session=session,
        plan_id=PLAN_ID,
        items=items,
    )

    result = schedule_operations_event_driven(
        items=items,
        rule=PriorityRule.FCFS,
        static_lot_priorities=(),
        ready_dispatch_provider=provider,
        resources={"TUNING_STATION": Resource("TUNING_STATION", 1)},
        calendar=WorkCalendar(),
        start_time=dt(9),
    )

    assert [operation.operation_id for operation in result.operations] == [
        "OP-102",
        "OP-101",
    ]
    assert result.operations[0].start == dt(9)
    assert result.operations[1].start == dt(9, 25)
    session.close()


def test_same_plan_task_reuses_confirmed_operation_tie_break() -> None:
    session = seeded_session()
    add_plan(session, include_lot_102=False)
    items = (
        tuning_item(
            "OP-U02",
            "LOT-101",
            "LOT-101-U02",
            state=OperationState.HOLD,
        ),
        tuning_item("OP-U01", "LOT-101", "LOT-101-U01"),
    )

    provider = build_plan_ready_dispatch_provider(
        session=session,
        plan_id=PLAN_ID,
        items=items,
    )

    assert provider(dt(9), items) == ("OP-U01", "OP-U02")
    session.close()


def test_provider_rejects_current_operation_missing_from_plan() -> None:
    session = seeded_session()
    add_plan(session, include_lot_102=False)
    items = (
        tuning_item("OP-101", "LOT-101", "LOT-101-U01"),
        tuning_item("OP-102", "LOT-102", "LOT-102-U01"),
    )

    with pytest.raises(ValueError, match="no matching ScheduleTask"):
        build_plan_ready_dispatch_provider(
            session=session,
            plan_id=PLAN_ID,
            items=items,
        )
    session.close()


def test_event_scheduler_rejects_incomplete_ready_provider_sequence() -> None:
    items = (
        tuning_item("OP-101", "LOT-101", "LOT-101-U01"),
        tuning_item("OP-102", "LOT-102", "LOT-102-U01"),
    )

    def incomplete_provider(_decision_time, _ready_items):
        return ("OP-101",)

    with pytest.raises(ValueError, match="each ready operation exactly once"):
        schedule_operations_event_driven(
            items=items,
            rule=PriorityRule.FCFS,
            static_lot_priorities=(),
            ready_dispatch_provider=incomplete_provider,
            resources={"TUNING_STATION": Resource("TUNING_STATION", 1)},
            calendar=WorkCalendar(),
            start_time=dt(9),
        )
