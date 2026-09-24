"""Project persisted WorkAttempt history into temporary scheduler execution order.

RoutingStep sequence remains master-data identity. Rework Attempts are inserted
into a calculation-only execution sequence on each projection.
"""

from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.orm import Session

from production_control.core.rework_core import ReworkRole
from production_control.domain.enums import OperationState
from production_control.persistence.models import (
    ProcessRow,
    RoutingStepRow,
    UnitOperationRow,
    WorkAttemptRow,
    WorkEventRow,
)


@dataclass(frozen=True, slots=True)
class ProjectedAttemptOrder:
    attempt_id: str
    unit_operation_id: str
    attempt_no: int
    step_seq: int
    process_code: str
    execution_seq: int
    rework_role: str | None
    is_current: bool
    operation_state: OperationState
    scheduler_blocked: bool


@dataclass(frozen=True, slots=True)
class UnitExecutionProjection:
    unit_id: str
    attempts: tuple[ProjectedAttemptOrder, ...]

    @property
    def scheduler_current_attempts(self) -> tuple[ProjectedAttemptOrder, ...]:
        return tuple(
            attempt
            for attempt in self.attempts
            if attempt.is_current
            and attempt.operation_state is not OperationState.COMPLETED
            and not attempt.scheduler_blocked
        )


@dataclass(frozen=True, slots=True)
class _AttemptRecord:
    attempt: WorkAttemptRow
    operation: UnitOperationRow
    step: RoutingStepRow
    process: ProcessRow


def _load_attempt_records(
    session: Session,
    *,
    unit_id: str,
) -> dict[str, _AttemptRecord]:
    operations = session.scalars(
        select(UnitOperationRow)
        .where(UnitOperationRow.unit_id == unit_id)
        .order_by(UnitOperationRow.routing_step_id)
    ).all()
    if not operations:
        raise ValueError(f"unit has no UnitOperation rows: {unit_id}")

    records: dict[str, _AttemptRecord] = {}
    for operation in operations:
        step = session.get(RoutingStepRow, operation.routing_step_id)
        if step is None:
            raise ValueError(
                "UnitOperation references missing RoutingStep: "
                f"{operation.routing_step_id}"
            )
        process = session.get(ProcessRow, step.process_id)
        if process is None:
            raise ValueError(
                f"RoutingStep references missing Process: {step.process_id}"
            )

        attempts = session.scalars(
            select(WorkAttemptRow)
            .where(
                WorkAttemptRow.unit_operation_id
                == operation.unit_operation_id
            )
            .order_by(WorkAttemptRow.attempt_no)
        ).all()
        if not attempts:
            raise ValueError(
                "UnitOperation has no WorkAttempt rows: "
                f"{operation.unit_operation_id}"
            )

        for attempt in attempts:
            if attempt.attempt_id in records:
                raise ValueError(f"duplicate attempt_id: {attempt.attempt_id}")
            records[attempt.attempt_id] = _AttemptRecord(
                attempt=attempt,
                operation=operation,
                step=step,
                process=process,
            )

    return records


def _base_attempt_ids(records: dict[str, _AttemptRecord]) -> list[str]:
    base = [
        record
        for record in records.values()
        if record.attempt.attempt_no == 1
    ]
    operation_ids = {record.operation.unit_operation_id for record in base}
    all_operation_ids = {
        record.operation.unit_operation_id for record in records.values()
    }
    if operation_ids != all_operation_ids:
        missing = ", ".join(sorted(all_operation_ids - operation_ids))
        raise ValueError(f"UnitOperation is missing Attempt 1: {missing}")

    base.sort(
        key=lambda record: (
            record.step.seq_no,
            record.operation.unit_operation_id,
        )
    )
    return [record.attempt.attempt_id for record in base]


def _rework_groups(
    session: Session,
    *,
    records: dict[str, _AttemptRecord],
) -> tuple[
    dict[str, list[_AttemptRecord]],
    dict[str, WorkEventRow],
]:
    groups: dict[str, list[_AttemptRecord]] = {}
    events: dict[str, WorkEventRow] = {}

    for record in records.values():
        if record.attempt.attempt_no == 1:
            continue
        if record.attempt.rework_role is None:
            raise ValueError(
                "non-initial WorkAttempt requires a rework_role for "
                "execution-order projection"
            )
        if record.attempt.rework_event_ref is None:
            raise ValueError("rework WorkAttempt is missing rework_event_ref")
        if record.attempt.rework_source_ref is None:
            raise ValueError("rework WorkAttempt is missing rework_source_ref")

        event_id = record.attempt.rework_event_ref
        source_event = events.get(event_id)
        if source_event is None:
            source_event = session.get(WorkEventRow, event_id)
            if source_event is None:
                raise ValueError(f"unknown rework source event: {event_id}")
            events[event_id] = source_event

        source_record = records.get(source_event.attempt_id)
        if source_record is None:
            raise ValueError(
                "rework source event belongs to an Attempt outside the Unit"
            )
        if (
            source_record.operation.unit_operation_id
            != record.attempt.rework_source_ref
        ):
            raise ValueError(
                "rework source operation does not match source event Attempt"
            )

        groups.setdefault(event_id, []).append(record)

    role_order = {
        ReworkRole.TUNING_REWORK.value: 0,
        ReworkRole.FINAL_TEST_RETEST.value: 1,
    }
    for event_id, group in groups.items():
        roles = [record.attempt.rework_role for record in group]
        if any(role not in role_order for role in roles):
            raise ValueError(
                f"unsupported rework role in execution projection: {event_id}"
            )
        if len(roles) != len(set(roles)):
            raise ValueError(
                f"duplicate rework role for source event: {event_id}"
            )
        group.sort(
            key=lambda record: (
                role_order[record.attempt.rework_role or ""],
                record.attempt.attempt_no,
                record.attempt.attempt_id,
            )
        )

    return groups, events


def _insert_rework_groups(
    *,
    base_order: list[str],
    groups: dict[str, list[_AttemptRecord]],
    events: dict[str, WorkEventRow],
) -> list[str]:
    order = list(base_order)
    pending = set(groups)

    while pending:
        progressed = False
        for event_id in sorted(
            pending,
            key=lambda candidate: (
                events[candidate].occurred_at,
                candidate,
            ),
        ):
            source_attempt_id = events[event_id].attempt_id
            if source_attempt_id not in order:
                continue

            source_index = order.index(source_attempt_id)
            insertion = [
                record.attempt.attempt_id
                for record in groups[event_id]
            ]
            order[source_index + 1 : source_index + 1] = insertion
            pending.remove(event_id)
            progressed = True
            break

        if not progressed:
            unresolved = ", ".join(sorted(pending))
            raise ValueError(
                "cannot resolve rework execution order for events: "
                f"{unresolved}"
            )

    return order


def _blocked_attempt_ids(
    *,
    records: dict[str, _AttemptRecord],
    groups: dict[str, list[_AttemptRecord]],
    events: dict[str, WorkEventRow],
) -> set[str]:
    blocked: set[str] = set()

    for event_id, group in groups.items():
        roles = {
            record.attempt.rework_role
            for record in group
        }
        if ReworkRole.TUNING_REWORK.value not in roles:
            continue
        if ReworkRole.FINAL_TEST_RETEST.value in roles:
            continue

        source_event = events[event_id]
        source_record = records[source_event.attempt_id]
        source_step_seq = source_record.step.seq_no

        for record in records.values():
            if not (
                record.attempt.attempt_no == 1
                and record.step.seq_no > source_step_seq
            ):
                continue
            if (
                record.attempt.attempt_no
                == record.operation.current_attempt_no
                and record.operation.state
                != OperationState.COMPLETED.value
            ):
                blocked.add(record.attempt.attempt_id)

    return blocked


def project_unit_execution_order(
    *,
    session: Session,
    unit_id: str,
) -> UnitExecutionProjection:
    """Build temporary, collision-free execution order for one Unit."""

    records = _load_attempt_records(session, unit_id=unit_id)
    base_order = _base_attempt_ids(records)
    groups, events = _rework_groups(session, records=records)
    ordered_attempt_ids = _insert_rework_groups(
        base_order=base_order,
        groups=groups,
        events=events,
    )
    blocked = _blocked_attempt_ids(
        records=records,
        groups=groups,
        events=events,
    )

    projected: list[ProjectedAttemptOrder] = []
    for execution_seq, attempt_id in enumerate(ordered_attempt_ids, start=1):
        record = records[attempt_id]
        projected.append(
            ProjectedAttemptOrder(
                attempt_id=attempt_id,
                unit_operation_id=record.operation.unit_operation_id,
                attempt_no=record.attempt.attempt_no,
                step_seq=record.step.seq_no,
                process_code=record.process.process_code,
                execution_seq=execution_seq,
                rework_role=record.attempt.rework_role,
                is_current=(
                    record.attempt.attempt_no
                    == record.operation.current_attempt_no
                ),
                operation_state=OperationState(record.operation.state),
                scheduler_blocked=attempt_id in blocked,
            )
        )

    return UnitExecutionProjection(
        unit_id=unit_id,
        attempts=tuple(projected),
    )
