from datetime import datetime
from zoneinfo import ZoneInfo

from production_control.core.calendar_engine import WorkCalendar
from production_control.core.dispatch_builder import OperationDispatchInput
from production_control.core.event_scheduler import EventDispatchInput, schedule_operations_event_driven
from production_control.core.finite_scheduler import OperationSpec
from production_control.core.priority_rules import LotPriorityInput, PriorityRule
from production_control.core.resource_engine import Resource
from production_control.core.slot_engine import ResourceRequirement
from production_control.core.urgent_dispatch_policy import (
    evaluate_urgent_lot_dispatch_policy,
)
from production_control.domain.enums import OperationState

SEOUL = ZoneInfo("Asia/Seoul")


def dt(hour: int, minute: int = 0) -> datetime:
    return datetime(2026, 10, 5, hour, minute, tzinfo=SEOUL)


def item(
    operation_id: str,
    lot_id: str,
    *,
    release_at: datetime,
    eligible_at: datetime | None = None,
) -> EventDispatchInput:
    return EventDispatchInput(
        operation=OperationSpec(
            operation_id=operation_id,
            lot_id=lot_id,
            unit_id=f"{lot_id}-U1",
            step_seq=1,
            process_code="TUNING",
            duration_minutes=30,
            requirements=(ResourceRequirement("TUNING_STATION"),),
            release_at=release_at,
        ),
        dispatch=OperationDispatchInput(
            operation_id=operation_id,
            lot_id=lot_id,
            unit_id=f"{lot_id}-U1",
            state=OperationState.WAITING,
            eligible_at=eligible_at or release_at,
        ),
    )


def priorities() -> tuple[LotPriorityInput, ...]:
    return (
        LotPriorityInput(
            lot_id="LOT-NORMAL",
            release_at=dt(8),
            deadline=dt(17),
            remaining_work_minutes=30,
            time_until_deadline_minutes=480,
        ),
        LotPriorityInput(
            lot_id="LOT-URGENT",
            release_at=dt(8, 30),
            deadline=dt(10),
            remaining_work_minutes=30,
            time_until_deadline_minutes=60,
        ),
    )


def build_schedule(
    *,
    rule: PriorityRule,
    urgent_eligible_at: datetime | None = None,
    capacity: int = 1,
):
    items = (
        item("NORMAL", "LOT-NORMAL", release_at=dt(8)),
        item(
            "URGENT",
            "LOT-URGENT",
            release_at=dt(8, 30),
            eligible_at=urgent_eligible_at,
        ),
    )
    resources = {"TUNING_STATION": Resource("TUNING_STATION", capacity)}
    calendar = WorkCalendar()
    schedule = schedule_operations_event_driven(
        items=items,
        rule=rule,
        static_lot_priorities=priorities(),
        resources=resources,
        calendar=calendar,
        start_time=dt(9),
    )
    return items, resources, calendar, schedule


def test_fcfs_is_rejected_when_nonurgent_ready_work_blocks_urgent_lot() -> None:
    items, resources, calendar, schedule = build_schedule(rule=PriorityRule.FCFS)

    result = evaluate_urgent_lot_dispatch_policy(
        items=items,
        schedule=schedule,
        resources=resources,
        calendar=calendar,
        urgent_lot_ids={"LOT-URGENT"},
    )

    assert [operation.operation_id for operation in schedule.operations] == [
        "NORMAL",
        "URGENT",
    ]
    assert result.compliant is False
    assert result.violation_reason is not None
    assert "LOT-URGENT" in result.violation_reason
    assert "LOT-NORMAL" in result.violation_reason


def test_edd_is_compliant_when_urgent_lot_uses_bottleneck_first() -> None:
    items, resources, calendar, schedule = build_schedule(rule=PriorityRule.EDD)

    result = evaluate_urgent_lot_dispatch_policy(
        items=items,
        schedule=schedule,
        resources=resources,
        calendar=calendar,
        urgent_lot_ids={"LOT-URGENT"},
    )

    assert [operation.operation_id for operation in schedule.operations] == [
        "URGENT",
        "NORMAL",
    ]
    assert result.compliant is True
    assert result.violation_reason is None


def test_parallel_capacity_does_not_create_false_policy_violation() -> None:
    items, resources, calendar, schedule = build_schedule(
        rule=PriorityRule.FCFS,
        capacity=2,
    )

    result = evaluate_urgent_lot_dispatch_policy(
        items=items,
        schedule=schedule,
        resources=resources,
        calendar=calendar,
        urgent_lot_ids={"LOT-URGENT"},
    )

    assert {operation.start for operation in schedule.operations} == {dt(9)}
    assert result.compliant is True


def test_nonurgent_may_run_while_urgent_operation_is_not_yet_eligible() -> None:
    items, resources, calendar, schedule = build_schedule(
        rule=PriorityRule.FCFS,
        urgent_eligible_at=dt(9, 30),
    )

    result = evaluate_urgent_lot_dispatch_policy(
        items=items,
        schedule=schedule,
        resources=resources,
        calendar=calendar,
        urgent_lot_ids={"LOT-URGENT"},
    )

    assert schedule.operations[0].operation_id == "NORMAL"
    assert result.compliant is True
