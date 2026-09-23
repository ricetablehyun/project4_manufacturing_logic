from datetime import datetime
from zoneinfo import ZoneInfo

from production_control.core.calendar_engine import WorkCalendar
from production_control.core.dispatch_builder import OperationDispatchInput
from production_control.core.event_scheduler import (
    EventDispatchInput,
    schedule_operations_event_driven,
)
from production_control.core.finite_scheduler import OperationSpec
from production_control.core.priority_rules import LotPriorityInput, PriorityRule
from production_control.core.resource_engine import Resource
from production_control.core.slot_engine import ResourceRequirement
from production_control.domain.enums import OperationState

SEOUL = ZoneInfo("Asia/Seoul")


def dt(hour: int, minute: int = 0) -> datetime:
    return datetime(2026, 10, 5, hour, minute, tzinfo=SEOUL)


def item(
    operation_id: str,
    lot_id: str,
    unit_id: str,
    *,
    step_seq: int = 1,
    duration: float = 30,
    release_at: datetime | None = None,
    eligible_at: datetime | None = None,
    resource_code: str = "WORKER_POOL",
    buffer_k: int | None = None,
) -> EventDispatchInput:
    release = release_at or dt(9)
    eligible = eligible_at or release
    return EventDispatchInput(
        operation=OperationSpec(
            operation_id=operation_id,
            lot_id=lot_id,
            unit_id=unit_id,
            step_seq=step_seq,
            process_code=f"STEP_{step_seq}",
            duration_minutes=duration,
            requirements=(ResourceRequirement(resource_code),),
            release_at=release,
            release_buffer_k=buffer_k,
        ),
        dispatch=OperationDispatchInput(
            operation_id=operation_id,
            lot_id=lot_id,
            unit_id=unit_id,
            state=OperationState.WAITING,
            eligible_at=eligible,
        ),
    )


def static_priority(
    lot_id: str,
    *,
    release_at: datetime | None = None,
    deadline: datetime | None = None,
) -> LotPriorityInput:
    return LotPriorityInput(
        lot_id=lot_id,
        release_at=release_at or dt(9),
        deadline=deadline or dt(17),
        remaining_work_minutes=60,
        time_until_deadline_minutes=480,
    )


def resources(capacity: int = 1) -> dict[str, Resource]:
    return {"WORKER_POOL": Resource("WORKER_POOL", capacity)}


def test_capacity_two_fills_two_jobs_at_same_decision_time() -> None:
    calls: list[datetime] = []

    def provider(
        decision_time: datetime,
        pending: tuple[OperationSpec, ...],
        scheduled: tuple,
    ) -> tuple[LotPriorityInput, ...]:
        calls.append(decision_time)
        return (
            static_priority("LOT-A"),
            static_priority("LOT-B"),
            static_priority("LOT-C"),
        )

    result = schedule_operations_event_driven(
        items=(
            item("A", "LOT-A", "U1"),
            item("B", "LOT-B", "U1"),
            item("C", "LOT-C", "U1"),
        ),
        rule=PriorityRule.SLACK,
        static_lot_priorities=(),
        dynamic_priority_provider=provider,
        resources=resources(capacity=2),
        calendar=WorkCalendar(),
        start_time=dt(9),
    )

    by_id = {operation.operation_id: operation for operation in result.operations}
    assert by_id["A"].start == dt(9)
    assert by_id["B"].start == dt(9)
    assert by_id["C"].start == dt(9, 30)
    assert calls.count(dt(9)) == 1


def test_dynamic_priority_is_recomputed_after_completion_event() -> None:
    calls: list[datetime] = []

    def provider(
        decision_time: datetime,
        pending: tuple[OperationSpec, ...],
        scheduled: tuple,
    ) -> tuple[LotPriorityInput, ...]:
        calls.append(decision_time)
        if decision_time == dt(9):
            return (
                LotPriorityInput("LOT-A", dt(9), dt(17), 100, 10),
                LotPriorityInput("LOT-B", dt(9), dt(17), 100, 20),
                LotPriorityInput("LOT-C", dt(9), dt(17), 100, 30),
            )
        return (
            LotPriorityInput("LOT-C", dt(9), dt(17), 100, 5),
            LotPriorityInput("LOT-B", dt(9), dt(17), 100, 20),
            LotPriorityInput("LOT-A", dt(9), dt(17), 100, 30),
        )

    result = schedule_operations_event_driven(
        items=(
            item("A", "LOT-A", "U1"),
            item("B", "LOT-B", "U1"),
            item("C", "LOT-C", "U1"),
        ),
        rule=PriorityRule.SLACK,
        static_lot_priorities=(),
        dynamic_priority_provider=provider,
        resources=resources(),
        calendar=WorkCalendar(),
        start_time=dt(9),
    )

    assert [operation.operation_id for operation in result.operations] == [
        "A",
        "C",
        "B",
    ]
    assert dt(9) in calls
    assert dt(9, 30) in calls


def test_same_timestamp_does_not_recalculate_after_first_parallel_start() -> None:
    call_count = 0

    def provider(
        decision_time: datetime,
        pending: tuple[OperationSpec, ...],
        scheduled: tuple,
    ) -> tuple[LotPriorityInput, ...]:
        nonlocal call_count
        call_count += 1
        order = (
            ("LOT-A", "LOT-B", "LOT-C")
            if call_count == 1
            else ("LOT-C", "LOT-B", "LOT-A")
        )

        return tuple(
            LotPriorityInput(
                lot_id=lot_id,
                release_at=dt(9),
                deadline=dt(17),
                remaining_work_minutes=100,
                time_until_deadline_minutes=index,
            )
            for index, lot_id in enumerate(order, start=1)
        )

    result = schedule_operations_event_driven(
        items=(
            item("A", "LOT-A", "U1"),
            item("B", "LOT-B", "U1"),
            item("C", "LOT-C", "U1"),
        ),
        rule=PriorityRule.SLACK,
        static_lot_priorities=(),
        dynamic_priority_provider=provider,
        resources=resources(capacity=2),
        calendar=WorkCalendar(),
        start_time=dt(9),
    )

    started_at_nine = [
        operation.operation_id
        for operation in result.operations
        if operation.start == dt(9)
    ]
    assert started_at_nine == ["A", "B"]


def test_fcfs_uses_static_priority_without_dynamic_provider() -> None:
    result = schedule_operations_event_driven(
        items=(
            item("LATE", "LOT-LATE", "U1"),
            item("EARLY", "LOT-EARLY", "U1"),
        ),
        rule=PriorityRule.FCFS,
        static_lot_priorities=(
            static_priority("LOT-LATE", release_at=dt(9, 10)),
            static_priority("LOT-EARLY", release_at=dt(9)),
        ),
        resources=resources(),
        calendar=WorkCalendar(),
        start_time=dt(9),
    )

    assert [operation.operation_id for operation in result.operations] == [
        "EARLY",
        "LATE",
    ]


def test_predecessor_releases_successor_at_completion_event() -> None:
    result = schedule_operations_event_driven(
        items=(
            item("S1", "LOT-A", "U1", step_seq=1, duration=20),
            item("S2", "LOT-A", "U1", step_seq=2, duration=20),
        ),
        rule=PriorityRule.FCFS,
        static_lot_priorities=(static_priority("LOT-A"),),
        resources=resources(),
        calendar=WorkCalendar(),
        start_time=dt(9),
    )

    by_id = {operation.operation_id: operation for operation in result.operations}
    assert by_id["S1"].start == dt(9)
    assert by_id["S1"].end == dt(9, 20)
    assert by_id["S2"].start == dt(9, 20)


def test_initial_buffer_releases_downstream_at_kth_completion() -> None:
    result = schedule_operations_event_driven(
        items=(
            item("U1-S1", "LOT-A", "U1", step_seq=1, duration=10),
            item("U2-S1", "LOT-A", "U2", step_seq=1, duration=10),
            item(
                "U1-S2",
                "LOT-A",
                "U1",
                step_seq=2,
                duration=10,
                resource_code="DOWNSTREAM",
                buffer_k=2,
            ),
            item(
                "U2-S2",
                "LOT-A",
                "U2",
                step_seq=2,
                duration=10,
                resource_code="DOWNSTREAM",
                buffer_k=2,
            ),
        ),
        rule=PriorityRule.FCFS,
        static_lot_priorities=(static_priority("LOT-A"),),
        resources={
            "WORKER_POOL": Resource("WORKER_POOL", 2),
            "DOWNSTREAM": Resource("DOWNSTREAM", 1),
        },
        calendar=WorkCalendar(),
        start_time=dt(9),
    )

    by_id = {operation.operation_id: operation for operation in result.operations}
    assert by_id["U1-S1"].end == dt(9, 10)
    assert by_id["U2-S1"].end == dt(9, 10)
    assert by_id["U1-S2"].start == dt(9, 10)


def test_future_release_advances_decision_clock() -> None:
    result = schedule_operations_event_driven(
        items=(
            item(
                "FUTURE",
                "LOT-A",
                "U1",
                release_at=dt(10),
                eligible_at=dt(10),
            ),
        ),
        rule=PriorityRule.EDD,
        static_lot_priorities=(static_priority("LOT-A"),),
        resources=resources(),
        calendar=WorkCalendar(),
        start_time=dt(9),
    )

    assert result.operations[0].start == dt(10)


def test_after_hours_start_advances_to_next_calendar_open() -> None:
    result = schedule_operations_event_driven(
        items=(item("A", "LOT-A", "U1", release_at=dt(9, 16)),),
        rule=PriorityRule.EDD,
        static_lot_priorities=(static_priority("LOT-A"),),
        resources=resources(),
        calendar=WorkCalendar(),
        start_time=dt(18),
    )

    assert result.operations[0].start == datetime(
        2026,
        10,
        6,
        9,
        0,
        tzinfo=SEOUL,
    )
