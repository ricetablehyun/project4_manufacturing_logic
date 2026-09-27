from datetime import datetime
from zoneinfo import ZoneInfo

import pytest
from sqlalchemy import select

from production_control.core.candidate_evaluator import CandidateKPI
from production_control.core.dispatch_builder import OperationDispatchInput
from production_control.core.event_scheduler import EventDispatchInput
from production_control.core.finite_scheduler import OperationSpec
from production_control.core.priority_rules import PriorityRule
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
    build_current_plan_ready_dispatch_provider,
)
from production_control.persistence.plan_lifecycle import (
    ApprovedPlanTaskDraft,
    load_current_approved_plan,
    persist_approved_replan,
)

SEOUL = ZoneInfo("Asia/Seoul")


def dt(hour: int, minute: int = 0) -> datetime:
    return datetime(2026, 10, 5, hour, minute, tzinfo=SEOUL)


def seeded_session():
    engine = create_sqlite_engine()
    create_schema(engine)
    session = create_session_factory(engine)()
    seed_f02_fixture(session)
    return session


def add_initial_plan(session) -> None:
    session.add(
        SchedulePlanRow(
            plan_id="PLAN-1",
            version=1,
            plan_kind="INITIAL",
            priority_rule="EDD",
            status="APPROVED",
            parent_plan_id=None,
            trigger_reason=None,
            created_at=dt(8),
            approved_at=dt(8),
            late_lot_count=1,
            total_tardiness_minutes=30,
            overtime_minutes=0,
            change_count=0,
        )
    )
    session.add_all(
        (
            ScheduleTaskRow(
                schedule_task_id="P1-LOT101-TUNING",
                plan_id="PLAN-1",
                lot_id="LOT-101",
                routing_step_id="STEP-04-TUNING",
                target_start=dt(9),
                target_end=dt(11),
                target_qty=4,
                priority_rank=1,
            ),
            ScheduleTaskRow(
                schedule_task_id="P1-LOT102-TUNING",
                plan_id="PLAN-1",
                lot_id="LOT-102",
                routing_step_id="STEP-04-TUNING",
                target_start=dt(11),
                target_end=dt(13),
                target_qty=4,
                priority_rank=2,
            ),
        )
    )
    session.commit()


def selected_kpi() -> CandidateKPI:
    return CandidateKPI(
        candidate_id="SLACK-CANDIDATE",
        late_lot_count=0,
        total_tardiness_minutes=0,
        overtime_minutes=30,
        change_count=2,
    )


def replan_tasks() -> tuple[ApprovedPlanTaskDraft, ...]:
    return (
        ApprovedPlanTaskDraft(
            schedule_task_id="P2-LOT102-TUNING",
            lot_id="LOT-102",
            routing_step_id="STEP-04-TUNING",
            target_start=dt(9),
            target_end=dt(11),
            target_qty=4,
            priority_rank=1,
        ),
        ApprovedPlanTaskDraft(
            schedule_task_id="P2-LOT101-TUNING",
            lot_id="LOT-101",
            routing_step_id="STEP-04-TUNING",
            target_start=dt(11),
            target_end=dt(13),
            target_qty=4,
            priority_rank=2,
        ),
    )


def approve_v2(session) -> SchedulePlanRow:
    return persist_approved_replan(
        session=session,
        plan_id="PLAN-2",
        parent_plan_id="PLAN-1",
        priority_rule=PriorityRule.SLACK,
        trigger_reason="URGENT_GATE_RISK",
        approved_at=dt(10),
        selected_kpi=selected_kpi(),
        tasks=replan_tasks(),
    )


def tuning_item(operation_id: str, lot_id: str, unit_id: str) -> EventDispatchInput:
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
            state=OperationState.WAITING,
            eligible_at=dt(9),
        ),
    )


def test_current_approved_plan_is_highest_approved_version() -> None:
    session = seeded_session()
    add_initial_plan(session)
    approve_v2(session)

    current = load_current_approved_plan(session=session)

    assert current.plan_id == "PLAN-2"
    assert current.version == 2
    session.close()


def test_current_approved_plan_rejects_ambiguous_latest_version() -> None:
    session = seeded_session()
    add_initial_plan(session)
    session.add_all(
        (
            SchedulePlanRow(
                plan_id="PLAN-2A",
                version=2,
                plan_kind="REPLAN",
                priority_rule="EDD",
                status="APPROVED",
                parent_plan_id="PLAN-1",
                created_at=dt(10),
                approved_at=dt(10),
            ),
            SchedulePlanRow(
                plan_id="PLAN-2B",
                version=2,
                plan_kind="REPLAN",
                priority_rule="SLACK",
                status="APPROVED",
                parent_plan_id="PLAN-1",
                created_at=dt(10),
                approved_at=dt(10),
            ),
        )
    )
    session.commit()

    with pytest.raises(ValueError, match="approved SchedulePlan version is ambiguous"):
        load_current_approved_plan(session=session)
    session.close()


def test_approval_persists_next_version_parent_kpi_and_tasks() -> None:
    session = seeded_session()
    add_initial_plan(session)

    plan = approve_v2(session)

    assert plan.version == 2
    assert plan.plan_kind == "REPLAN"
    assert plan.priority_rule == "SLACK"
    assert plan.status == "APPROVED"
    assert plan.parent_plan_id == "PLAN-1"
    assert plan.trigger_reason == "URGENT_GATE_RISK"
    assert plan.late_lot_count == 0
    assert plan.total_tardiness_minutes == 0
    assert plan.overtime_minutes == 30
    assert plan.change_count == 2

    old = session.get(SchedulePlanRow, "PLAN-1")
    assert old is not None
    assert old.status == "APPROVED"

    tasks = session.scalars(
        select(ScheduleTaskRow)
        .where(ScheduleTaskRow.plan_id == "PLAN-2")
        .order_by(ScheduleTaskRow.priority_rank)
    ).all()
    assert [task.lot_id for task in tasks] == ["LOT-102", "LOT-101"]
    assert [task.target_qty for task in tasks] == [4, 4]
    session.close()


def test_approval_requires_parent_to_be_current_plan() -> None:
    session = seeded_session()
    add_initial_plan(session)
    approve_v2(session)

    with pytest.raises(ValueError, match="replan parent must be the current approved plan"):
        persist_approved_replan(
            session=session,
            plan_id="PLAN-3",
            parent_plan_id="PLAN-1",
            priority_rule=PriorityRule.CR,
            trigger_reason="URGENT_GATE_RISK",
            approved_at=dt(12),
            selected_kpi=selected_kpi(),
            tasks=(
                ApprovedPlanTaskDraft(
                    schedule_task_id="P3-LOT101-TUNING",
                    lot_id="LOT-101",
                    routing_step_id="STEP-04-TUNING",
                    target_start=dt(12),
                    target_end=dt(14),
                    target_qty=4,
                    priority_rank=1,
                ),
            ),
        )
    session.close()


def test_approval_rejects_duplicate_lot_routing_step_task() -> None:
    session = seeded_session()
    add_initial_plan(session)
    duplicate_tasks = (
        ApprovedPlanTaskDraft(
            schedule_task_id="P2-A",
            lot_id="LOT-101",
            routing_step_id="STEP-04-TUNING",
            target_start=dt(9),
            target_end=dt(10),
            target_qty=2,
            priority_rank=1,
        ),
        ApprovedPlanTaskDraft(
            schedule_task_id="P2-B",
            lot_id="LOT-101",
            routing_step_id="STEP-04-TUNING",
            target_start=dt(10),
            target_end=dt(11),
            target_qty=2,
            priority_rank=2,
        ),
    )

    with pytest.raises(ValueError, match="one task per LOT x RoutingStep"):
        persist_approved_replan(
            session=session,
            plan_id="PLAN-2",
            parent_plan_id="PLAN-1",
            priority_rule=PriorityRule.EDD,
            trigger_reason="URGENT_GATE_RISK",
            approved_at=dt(10),
            selected_kpi=selected_kpi(),
            tasks=duplicate_tasks,
        )
    session.close()


def test_live_dispatch_uses_latest_approved_version_after_approval() -> None:
    session = seeded_session()
    add_initial_plan(session)
    approve_v2(session)
    items = (
        tuning_item("OP-101", "LOT-101", "LOT-101-U01"),
        tuning_item("OP-102", "LOT-102", "LOT-102-U01"),
    )

    provider = build_current_plan_ready_dispatch_provider(
        session=session,
        items=items,
    )

    assert provider(dt(10), items) == ("OP-102", "OP-101")
    session.close()
