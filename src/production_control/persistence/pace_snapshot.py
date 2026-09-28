"""Build current LOT x process Pace snapshots from persisted execution facts."""

from datetime import datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from production_control.core.pace_estimator import PaceForecast, estimate_lot_process_work
from production_control.domain.enums import OperationState
from production_control.persistence.models import (
    LotRow,
    ProcessRow,
    RoutingStepRow,
    UnitOperationRow,
    UnitRow,
    WorkAttemptRow,
    WorkEventRow,
)

_ACTIVE_START_EVENTS = ("START", "RESUME")


def effective_attempt_active_minutes(
    *,
    session: Session,
    attempt: WorkAttemptRow,
    operation_state: OperationState,
    as_of: datetime,
) -> float:
    """Return persisted active minutes plus the open RUNNING segment up to ``as_of``."""

    if as_of.tzinfo is None or as_of.utcoffset() is None:
        raise ValueError("as_of must be timezone-aware")

    active_minutes = float(attempt.active_minutes)
    if operation_state is not OperationState.RUNNING:
        return active_minutes

    active_start = session.scalar(
        select(WorkEventRow)
        .where(
            WorkEventRow.attempt_id == attempt.attempt_id,
            WorkEventRow.event_type.in_(_ACTIVE_START_EVENTS),
        )
        .order_by(WorkEventRow.occurred_at.desc(), WorkEventRow.event_id.desc())
    )
    if active_start is None:
        raise ValueError(
            f"RUNNING WorkAttempt has no START/RESUME event: {attempt.attempt_id}"
        )
    if as_of < active_start.occurred_at:
        raise ValueError(
            "as_of cannot be earlier than the current RUNNING segment start: "
            f"{attempt.attempt_id}"
        )

    return active_minutes + (
        as_of - active_start.occurred_at
    ).total_seconds() / 60.0


def load_lot_process_pace_forecasts(
    *,
    session: Session,
    lot_id: str,
    pace_min_samples: int,
    as_of: datetime,
) -> dict[str, PaceForecast]:
    """Load the current Pace forecast for every internal process in one LOT.

    Initial normal Attempts are the Pace-learning population. Confirmed rework
    Attempts remain separate future workload and therefore do not change the
    normal LOT x process Pace sample set here.
    """

    lot = session.get(LotRow, lot_id)
    if lot is None:
        raise ValueError(f"unknown lot_id: {lot_id}")

    rows = session.execute(
        select(UnitOperationRow, WorkAttemptRow, RoutingStepRow, ProcessRow)
        .join(UnitRow, UnitOperationRow.unit_id == UnitRow.unit_id)
        .join(
            RoutingStepRow,
            UnitOperationRow.routing_step_id == RoutingStepRow.routing_step_id,
        )
        .join(ProcessRow, RoutingStepRow.process_id == ProcessRow.process_id)
        .join(
            WorkAttemptRow,
            WorkAttemptRow.unit_operation_id == UnitOperationRow.unit_operation_id,
        )
        .where(
            UnitRow.lot_id == lot_id,
            RoutingStepRow.duration_mode == "UNIT_TIME",
            WorkAttemptRow.rework_role.is_(None),
        )
        .order_by(
            RoutingStepRow.seq_no,
            UnitOperationRow.unit_operation_id,
            WorkAttemptRow.attempt_no,
        )
    ).all()
    if not rows:
        raise ValueError(f"LOT has no persisted internal Attempts: {lot_id}")

    standard_by_process: dict[str, float] = {}
    completed_by_process: dict[str, list[float]] = {}
    cumulative_by_process: dict[str, float] = {}

    for operation, attempt, step, process in rows:
        if step.standard_minutes is None or step.standard_minutes <= 0:
            raise ValueError(
                f"UNIT_TIME step is missing standard_minutes: {step.routing_step_id}"
            )

        existing_standard = standard_by_process.get(process.process_code)
        if (
            existing_standard is not None
            and existing_standard != float(step.standard_minutes)
        ):
            raise ValueError(
                "one process_code maps to multiple standard_minutes within LOT: "
                f"{lot_id} / {process.process_code}"
            )
        standard_by_process[process.process_code] = float(step.standard_minutes)

        is_current_attempt = operation.current_attempt_no == attempt.attempt_no
        operation_state = (
            OperationState(operation.state)
            if is_current_attempt
            else OperationState.COMPLETED
        )
        active_minutes = effective_attempt_active_minutes(
            session=session,
            attempt=attempt,
            operation_state=operation_state,
            as_of=as_of,
        )
        cumulative_by_process[process.process_code] = (
            cumulative_by_process.get(process.process_code, 0.0) + active_minutes
        )

        if attempt.ended_at is not None and active_minutes > 0:
            completed_by_process.setdefault(process.process_code, []).append(
                active_minutes
            )

    return {
        process_code: estimate_lot_process_work(
            planned_unit_count=lot.quantity,
            standard_minutes_per_unit=standard_minutes,
            completed_active_minutes=completed_by_process.get(process_code, ()),
            pace_min_samples=pace_min_samples,
            cumulative_actual_active_minutes=cumulative_by_process.get(
                process_code,
                0.0,
            ),
        )
        for process_code, standard_minutes in standard_by_process.items()
    }
