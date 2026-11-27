"""Discrete-event virtual plant.

The plant is the controlled process of the closed loop. It owns simulated time
and the physical execution of operations: an operation starts only when the
shop floor receives a work order, then runs for its hidden true duration
(``TruthModel``), pausing outside working hours exactly like the system's own
calendar assumption. The plant does not decide what to run next.

The plant also checks physical feasibility independently of the planning
system. Any start that would exceed a resource's capacity or skip a routing
predecessor is recorded as a violation, so the closed-loop runs double as a
constraint audit of the plan the system issued.
"""

from collections.abc import Iterable, Mapping
from dataclasses import dataclass, field
from datetime import datetime

from production_control.core.calendar_engine import WorkCalendar
from production_control.sim.truth import TruthModel


@dataclass(frozen=True, slots=True)
class OperationSpec:
    """Static physical description of one Unit operation."""

    unit_operation_id: str
    lot_id: str
    unit_id: str
    unit_code: str
    process_code: str
    seq_no: int
    standard_minutes: float
    resource_codes: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class PlantLayout:
    capacities: Mapping[str, int]
    operations: Mapping[str, OperationSpec]

    def unit_operations(self, unit_id: str) -> tuple[OperationSpec, ...]:
        return tuple(
            sorted(
                (spec for spec in self.operations.values() if spec.unit_id == unit_id),
                key=lambda spec: spec.seq_no,
            )
        )


@dataclass(frozen=True, slots=True)
class RunningOperation:
    unit_operation_id: str
    attempt_no: int
    started_at: datetime
    finishes_at: datetime
    true_minutes: float
    plan_version: int | None


@dataclass(frozen=True, slots=True)
class ExecutionRecord:
    """One physical execution interval, as it actually happened in the plant."""

    unit_operation_id: str
    lot_id: str
    unit_id: str
    unit_code: str
    process_code: str
    attempt_no: int
    started_at: datetime
    finished_at: datetime
    true_minutes: float
    result: str | None
    plan_version: int | None


@dataclass
class VirtualPlant:
    layout: PlantLayout
    calendar: WorkCalendar
    truth: TruthModel
    clock: datetime
    running: dict[str, RunningOperation] = field(default_factory=dict)
    completed_attempts: dict[str, int] = field(default_factory=dict)
    records: list[ExecutionRecord] = field(default_factory=list)
    violations: list[str] = field(default_factory=list)

    def __post_init__(self) -> None:
        if self.clock.tzinfo is None or self.clock.utcoffset() is None:
            raise ValueError("plant clock must be timezone-aware")

    # ------------------------------------------------------------------ time
    def advance_to(self, moment: datetime) -> None:
        if moment < self.clock:
            raise ValueError(f"plant time cannot move backwards: {moment} < {self.clock}")
        self.clock = moment

    def next_completion_at(self) -> datetime | None:
        if not self.running:
            return None
        return min(item.finishes_at for item in self.running.values())

    # ------------------------------------------------------------- resources
    def resources_in_use(self) -> dict[str, int]:
        used: dict[str, int] = {}
        for item in self.running.values():
            for code in self.layout.operations[item.unit_operation_id].resource_codes:
                used[code] = used.get(code, 0) + 1
        return used

    def _check_start_feasible(self, spec: OperationSpec, attempt_no: int) -> None:
        if spec.unit_operation_id in self.running:
            self.violations.append(
                f"{self.clock.isoformat()} {spec.unit_operation_id} started while running"
            )
        used = self.resources_in_use()
        for code in spec.resource_codes:
            capacity = self.layout.capacities.get(code, 0)
            if used.get(code, 0) + 1 > capacity:
                self.violations.append(
                    f"{self.clock.isoformat()} {spec.unit_operation_id} exceeds "
                    f"{code} capacity {capacity}"
                )
        if attempt_no == 1:
            for predecessor in self.layout.unit_operations(spec.unit_id):
                if predecessor.seq_no >= spec.seq_no:
                    break
                if predecessor.unit_operation_id not in self.completed_attempts:
                    self.violations.append(
                        f"{self.clock.isoformat()} {spec.unit_operation_id} started before "
                        f"predecessor {predecessor.unit_operation_id} completed"
                    )

    # ------------------------------------------------------------ execution
    def adopt_running(
        self,
        *,
        unit_operation_id: str,
        attempt_no: int,
        started_at: datetime,
        elapsed_active_minutes: float,
        plan_version: int | None,
    ) -> RunningOperation:
        """Take over an operation that was already RUNNING when the run began."""

        spec = self.layout.operations[unit_operation_id]
        true_minutes = self.truth.true_minutes(
            unit_operation_id=unit_operation_id,
            attempt_no=attempt_no,
            standard_minutes=spec.standard_minutes,
        )
        remaining = max(true_minutes - elapsed_active_minutes, 0.0)
        finishes_at = (
            self.clock
            if remaining == 0
            else self.calendar.add_working_minutes(self.clock, remaining)
        )
        running = RunningOperation(
            unit_operation_id=unit_operation_id,
            attempt_no=attempt_no,
            started_at=started_at,
            finishes_at=finishes_at,
            true_minutes=true_minutes,
            plan_version=plan_version,
        )
        self.running[unit_operation_id] = running
        return running

    def start(
        self,
        *,
        unit_operation_id: str,
        attempt_no: int,
        plan_version: int | None,
    ) -> RunningOperation:
        spec = self.layout.operations.get(unit_operation_id)
        if spec is None:
            raise KeyError(f"work order for unknown operation: {unit_operation_id}")
        if not self.calendar.is_working_time(self.clock):
            self.violations.append(
                f"{self.clock.isoformat()} {unit_operation_id} started outside working time"
            )
        self._check_start_feasible(spec, attempt_no)
        true_minutes = self.truth.true_minutes(
            unit_operation_id=unit_operation_id,
            attempt_no=attempt_no,
            standard_minutes=spec.standard_minutes,
        )
        running = RunningOperation(
            unit_operation_id=unit_operation_id,
            attempt_no=attempt_no,
            started_at=self.clock,
            finishes_at=self.calendar.add_working_minutes(self.clock, true_minutes),
            true_minutes=true_minutes,
            plan_version=plan_version,
        )
        self.running[unit_operation_id] = running
        return running

    def true_remaining_minutes(self, unit_operation_id: str) -> float:
        running = self.running[unit_operation_id]
        if running.finishes_at <= self.clock:
            return 0.0
        return self.calendar.working_minutes_between(self.clock, running.finishes_at)

    def finish_due(self) -> tuple[ExecutionRecord, ...]:
        """Finish every running operation whose true end is the current time."""

        due = sorted(
            (item for item in self.running.values() if item.finishes_at <= self.clock),
            key=lambda item: (item.finishes_at, item.unit_operation_id),
        )
        finished: list[ExecutionRecord] = []
        for item in due:
            del self.running[item.unit_operation_id]
            spec = self.layout.operations[item.unit_operation_id]
            result: str | None = None
            if spec.process_code == "FINAL_TEST":
                passed = self.truth.final_test_passes(
                    unit_operation_id=item.unit_operation_id,
                    attempt_no=item.attempt_no,
                )
                result = "PASS" if passed else "FAIL"
            if result != "FAIL":
                self.completed_attempts[item.unit_operation_id] = item.attempt_no
            record = ExecutionRecord(
                unit_operation_id=item.unit_operation_id,
                lot_id=spec.lot_id,
                unit_id=spec.unit_id,
                unit_code=spec.unit_code,
                process_code=spec.process_code,
                attempt_no=item.attempt_no,
                started_at=item.started_at,
                finished_at=item.finishes_at,
                true_minutes=item.true_minutes,
                result=result,
                plan_version=item.plan_version,
            )
            self.records.append(record)
            finished.append(record)
        return tuple(finished)

    def mark_completed(self, unit_operation_ids: Iterable[str]) -> None:
        """Record operations that were already complete when the run began."""

        for unit_operation_id in unit_operation_ids:
            self.completed_attempts.setdefault(unit_operation_id, 1)
