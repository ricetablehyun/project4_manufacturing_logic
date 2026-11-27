"""Closed-loop run: virtual plant <-> production-control API <-> manager.

One decision step at simulated time ``t``:

1. the plant finishes every operation whose hidden true end is ``t`` and the
   terminal reports COMPLETE / PASS / FAIL;
2. if the system cannot forecast because a RUNNING operation has exceeded its
   Pace, the worker answers with an expected remaining time (D069);
3. the manager reviews the Forecast when something happened (start of run,
   start of a working day, a worker delay estimate, a FINAL_TEST failure) and
   approves a candidate according to the policy under test;
4. the terminal fetches the work orders of the *current* approved plan and the
   plant starts exactly those operations;
5. time advances to the next completion, the next planned start or the next
   working-day opening.

Nothing in the loop reads the system's database directly. Initial layout data
(routing, standard times, capacities) is read once to build the physical plant.
"""

from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import datetime, time, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from production_control.core.calendar_engine import WorkCalendar
from production_control.persistence.mappers import load_work_calendar
from production_control.persistence.models import (
    ProcessRow,
    ResourceRow,
    RoutingStepResourceRow,
    RoutingStepRow,
    UnitOperationRow,
    UnitRow,
)
from production_control.sim.manager import ApprovalPolicy, ReviewRecord, review
from production_control.sim.plant import OperationSpec, PlantLayout, VirtualPlant
from production_control.sim.terminal import CallCounter, ShopFloorTerminal


class ClosedLoopError(RuntimeError):
    """The closed loop reached a state it cannot make progress from."""


def build_plant_layout(session: Session) -> PlantLayout:
    """Read routing, standard times and capacities once to build the plant."""

    capacities = {
        row.resource_code: row.capacity
        for row in session.scalars(select(ResourceRow).where(ResourceRow.active.is_(True)))
    }
    resources_by_step: dict[str, list[str]] = {}
    for step_id, code in session.execute(
        select(RoutingStepResourceRow.routing_step_id, ResourceRow.resource_code).join(
            ResourceRow, RoutingStepResourceRow.resource_id == ResourceRow.resource_id
        )
    ):
        resources_by_step.setdefault(step_id, []).append(code)

    operations: dict[str, OperationSpec] = {}
    rows = session.execute(
        select(UnitOperationRow, UnitRow, RoutingStepRow, ProcessRow)
        .join(UnitRow, UnitOperationRow.unit_id == UnitRow.unit_id)
        .join(RoutingStepRow, UnitOperationRow.routing_step_id == RoutingStepRow.routing_step_id)
        .join(ProcessRow, RoutingStepRow.process_id == ProcessRow.process_id)
    ).all()
    for operation, unit, step, process in rows:
        if step.standard_minutes is None:
            continue
        operations[operation.unit_operation_id] = OperationSpec(
            unit_operation_id=operation.unit_operation_id,
            lot_id=unit.lot_id,
            unit_id=unit.unit_id,
            unit_code=unit.unit_code,
            process_code=process.process_code,
            seq_no=step.seq_no,
            standard_minutes=float(step.standard_minutes),
            resource_codes=tuple(sorted(resources_by_step.get(step.routing_step_id, ()))),
        )
    return PlantLayout(capacities=capacities, operations=operations)


def load_plant_calendar(session: Session, calendar_id: str) -> WorkCalendar:
    return load_work_calendar(session, calendar_id)


@dataclass
class ClockHolder:
    """Mutable simulated clock shared by the plant and the API server."""

    now: datetime

    def __call__(self) -> datetime:
        return self.now


@dataclass
class RunResult:
    policy: ApprovalPolicy
    started_at: datetime
    finished_at: datetime
    plant: VirtualPlant
    reviews: list[ReviewRecord]
    calls: CallCounter
    steps: int
    final_plan_version: int
    estimates: list[tuple[datetime, str, float, float]] = field(default_factory=list)

    @property
    def violations(self) -> list[str]:
        return self.plant.violations

    @property
    def approvals(self) -> list[ReviewRecord]:
        return [item for item in self.reviews if item.action == "APPROVED"]


def _next_opening_after(calendar: WorkCalendar, moment: datetime) -> datetime:
    local = moment.astimezone(calendar.tz)
    if calendar.is_working_time(local):
        tomorrow = datetime.combine(local.date() + timedelta(days=1), time.min, tzinfo=calendar.tz)
        return calendar.next_work_start(tomorrow)
    return calendar.next_work_start(local)


def _adopt_initial_state(
    *,
    terminal: ShopFloorTerminal,
    plant: VirtualPlant,
    calendar: WorkCalendar,
    plan_version: int,
) -> None:
    completed: list[str] = []
    for row in terminal.unit_operations():
        operation_id = row["operation_id"]
        if operation_id not in plant.layout.operations:
            continue
        state = row["state"]
        if state == "COMPLETED":
            completed.append(operation_id)
        elif state == "RUNNING":
            elapsed = float(row["active_minutes"])
            last_event_at = row["last_event_at"]
            if last_event_at is not None:
                opened = datetime.fromisoformat(last_event_at)
                if opened < plant.clock:
                    elapsed += calendar.working_minutes_between(opened, plant.clock)
            plant.adopt_running(
                unit_operation_id=operation_id,
                attempt_no=int(row["attempt_no"]),
                started_at=datetime.fromisoformat(last_event_at) if last_event_at else plant.clock,
                elapsed_active_minutes=elapsed,
                plan_version=plan_version,
            )
        elif state == "HOLD":
            raise ClosedLoopError(
                f"closed-loop runs do not start from HOLD operations: {operation_id}"
            )
    plant.mark_completed(completed)


def _all_work_completed(terminal: ShopFloorTerminal, plant: VirtualPlant) -> bool:
    if plant.running:
        return False
    for row in terminal.unit_operations():
        if row["operation_id"] not in plant.layout.operations:
            continue
        if row["state"] != "COMPLETED":
            return False
        if row["process_code"] == "FINAL_TEST" and row["result"] != "PASS":
            return False
    return True


def run_closed_loop(
    *,
    terminal: ShopFloorTerminal,
    plant: VirtualPlant,
    clock: ClockHolder,
    policy: ApprovalPolicy,
    review_daily: bool = True,
    max_steps: int = 20_000,
    on_step: Callable[[datetime], None] | None = None,
) -> RunResult:
    """Run the plant until every operation has finished (FINAL_TEST passed)."""

    calendar = plant.calendar
    started_at = plant.clock
    clock.now = plant.clock
    plan = terminal.current_plan()
    _adopt_initial_state(
        terminal=terminal,
        plant=plant,
        calendar=calendar,
        plan_version=plan["version"],
    )

    reviews: list[ReviewRecord] = []
    estimates: list[tuple[datetime, str, float, float]] = []
    estimate_rounds: dict[tuple[str, int], int] = {}
    triggers: list[str] = ["RUN_START"]
    last_daily_review: object = None
    steps = 0

    while True:
        steps += 1
        if steps > max_steps:
            raise ClosedLoopError(f"closed loop exceeded {max_steps} decision steps")
        t = plant.clock
        clock.now = t
        if on_step is not None:
            on_step(t)

        # 1. report what physically finished at t
        for record in plant.finish_due():
            event_type = record.result or "COMPLETE"
            terminal.report(
                unit_operation_id=record.unit_operation_id,
                attempt_no=record.attempt_no,
                event_type=event_type,
                occurred_at=record.finished_at,
                reason="SIM_FINAL_TEST_FAIL" if event_type == "FAIL" else None,
            )
            if event_type == "FAIL":
                triggers.append("FINAL_TEST_FAIL")

        if not plant.running and _all_work_completed(terminal, plant):
            break

        working = calendar.is_working_time(t)
        if review_daily and working and t.date() != last_daily_review:
            last_daily_review = t.date()
            triggers.append("DAILY_REVIEW")

        # 2. resolve Pace-overrun questions so the system can forecast
        orders_payload: dict | None = None
        if working or triggers:
            for _ in range(5):
                orders_payload = terminal.work_orders(t)
                if orders_payload["readiness"] == "READY":
                    break
                waiting = orders_payload["waiting_operation_ids"]
                if not waiting:
                    raise ClosedLoopError(
                        f"Forecast is {orders_payload['readiness']} at {t} with no worker action"
                    )
                for operation_id in waiting:
                    running = plant.running.get(operation_id)
                    if running is None:
                        raise ClosedLoopError(
                            f"system asks for remaining time of a non-running operation: "
                            f"{operation_id}"
                        )
                    key = (operation_id, running.attempt_no)
                    estimate_rounds[key] = estimate_rounds.get(key, 0) + 1
                    true_remaining = plant.true_remaining_minutes(operation_id)
                    estimate = plant.truth.worker_estimate(
                        unit_operation_id=operation_id,
                        attempt_no=running.attempt_no,
                        true_remaining_minutes=true_remaining,
                        estimate_round=estimate_rounds[key],
                    )
                    terminal.estimate_remaining(unit_operation_id=operation_id, minutes=estimate)
                    estimates.append((t, operation_id, estimate, true_remaining))
                triggers.append("DELAY_ESTIMATE")
            else:
                raise ClosedLoopError(f"Forecast stayed WAIT after worker estimates at {t}")

        # 3. manager review
        if triggers:
            record = review(
                terminal=terminal,
                at=t,
                trigger="+".join(dict.fromkeys(triggers)),
                policy=policy,
            )
            reviews.append(record)
            triggers = []
            if record.action == "APPROVED" and working:
                orders_payload = terminal.work_orders(t)

        # 4. execute the current plan's work orders
        next_start_at: datetime | None = None
        if working and orders_payload is not None:
            plan_version = orders_payload["plan_version"]
            for order in orders_payload["orders"]:
                attempt_no = int(order["attempt_id"].rsplit("::", 1)[1])
                plant.start(
                    unit_operation_id=order["unit_operation_id"],
                    attempt_no=attempt_no,
                    plan_version=plan_version,
                )
                terminal.report(
                    unit_operation_id=order["unit_operation_id"],
                    attempt_no=attempt_no,
                    event_type="START",
                    occurred_at=t,
                )
            if orders_payload.get("next_start_at"):
                next_start_at = datetime.fromisoformat(orders_payload["next_start_at"])

        if (
            working
            and not plant.running
            and next_start_at is None
            and orders_payload is not None
            and not orders_payload["orders"]
        ):
            raise ClosedLoopError(
                f"plant is idle at {t} with unfinished work and no planned start"
            )

        # 5. advance time
        candidates: list[datetime] = []
        completion = plant.next_completion_at()
        if completion is not None:
            candidates.append(completion)
        if next_start_at is not None and next_start_at > t:
            candidates.append(next_start_at)
        if not working:
            candidates.append(calendar.next_work_start(t))
        if review_daily:
            candidates.append(_next_opening_after(calendar, t))
        future = [moment for moment in candidates if moment > t]
        if not future:
            raise ClosedLoopError(f"no future event at {t}; plant is idle with work left")
        plant.advance_to(min(future))

    return RunResult(
        policy=policy,
        started_at=started_at,
        finished_at=plant.clock,
        plant=plant,
        reviews=reviews,
        calls=terminal.calls,
        steps=steps,
        final_plan_version=terminal.current_plan()["version"],
        estimates=estimates,
    )
