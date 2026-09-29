"""Application-level Live Forecast orchestration over persisted production state."""

from dataclasses import dataclass
from datetime import datetime
from math import isfinite

from sqlalchemy import select
from sqlalchemy.orm import Session

from production_control.core.event_scheduler import schedule_operations_event_driven
from production_control.core.pace_scheduler_adapter import ForecastReadiness
from production_control.core.priority_rules import PriorityRule
from production_control.domain.enums import OperationState
from production_control.persistence.forecast_input_bundle import (
    build_internal_lot_forecast_inputs,
)
from production_control.persistence.forecast_result import (
    PersistedForecastResult,
    evaluate_persisted_forecast,
)
from production_control.persistence.mappers import load_active_resources, load_work_calendar
from production_control.persistence.models import (
    UnitOperationRow,
    UnitRow,
    WorkAttemptRow,
    WorkEventRow,
)
from production_control.persistence.pace_snapshot import (
    load_lot_process_pace_forecasts,
)
from production_control.persistence.plan_dispatch import (
    build_plan_ready_dispatch_provider,
    load_plan_task_priorities,
)
from production_control.persistence.plan_lifecycle import load_current_approved_plan


@dataclass(frozen=True, slots=True)
class LiveForecastConfig:
    """Application configuration whose numeric values remain project parameters."""

    calendar_id: str
    pace_min_samples: int
    warning_threshold_minutes: float

    def __post_init__(self) -> None:
        if not self.calendar_id:
            raise ValueError("calendar_id must not be empty")
        if self.pace_min_samples <= 0:
            raise ValueError("pace_min_samples must be greater than 0")
        if (
            self.warning_threshold_minutes < 0
            or not isfinite(self.warning_threshold_minutes)
        ):
            raise ValueError(
                "warning_threshold_minutes must be finite and 0 or greater"
            )


@dataclass(frozen=True, slots=True)
class LiveForecastSnapshot:
    plan_id: str
    plan_version: int
    as_of: datetime
    readiness: ForecastReadiness
    result: PersistedForecastResult | None
    waiting_operation_ids: tuple[str, ...] = ()


def _validate_as_of_against_current_state(
    *,
    session: Session,
    lot_ids: tuple[str, ...],
    as_of: datetime,
) -> None:
    """Reject historical time travel against a newer persisted execution state."""

    if as_of.tzinfo is None or as_of.utcoffset() is None:
        raise ValueError("as_of must be timezone-aware")
    if not lot_ids:
        return

    latest_event_at = session.scalar(
        select(WorkEventRow.occurred_at)
        .join(WorkAttemptRow, WorkEventRow.attempt_id == WorkAttemptRow.attempt_id)
        .join(
            UnitOperationRow,
            WorkAttemptRow.unit_operation_id == UnitOperationRow.unit_operation_id,
        )
        .join(UnitRow, UnitOperationRow.unit_id == UnitRow.unit_id)
        .where(UnitRow.lot_id.in_(lot_ids))
        .order_by(WorkEventRow.occurred_at.desc(), WorkEventRow.event_id.desc())
        .limit(1)
    )
    if latest_event_at is not None and as_of < latest_event_at:
        raise ValueError(
            "as_of cannot be earlier than the latest persisted WorkEvent for "
            "the current execution state"
        )


def _worker_actionable_waiting_attempt_ids(
    *,
    session: Session,
    waiting_attempt_ids: list[str],
) -> tuple[str, ...]:
    """Expose only WAIT blockers that D069 lets a worker resolve.

    The Pace adapter can stay WAIT for other conservative reasons, including an
    exhausted aggregate work budget with unfinished operations. Those are not
    worker residual-time questions and must not be rendered as dozens of false
    operator actions.
    """

    if not waiting_attempt_ids:
        return ()

    rows = session.scalars(
        select(WorkAttemptRow.attempt_id)
        .join(
            UnitOperationRow,
            WorkAttemptRow.unit_operation_id == UnitOperationRow.unit_operation_id,
        )
        .where(
            WorkAttemptRow.attempt_id.in_(set(waiting_attempt_ids)),
            UnitOperationRow.state == OperationState.RUNNING.value,
        )
    ).all()
    return tuple(sorted(set(rows)))


def build_live_forecast(
    *,
    session: Session,
    as_of: datetime,
    config: LiveForecastConfig,
) -> LiveForecastSnapshot:
    """Calculate Live Forecast for all LOTs in the latest approved plan."""

    current_plan = load_current_approved_plan(session=session)
    priorities = load_plan_task_priorities(
        session=session,
        plan_id=current_plan.plan_id,
    )
    lot_ids = tuple(dict.fromkeys(priority.lot_id for priority in priorities))
    _validate_as_of_against_current_state(
        session=session,
        lot_ids=lot_ids,
        as_of=as_of,
    )

    items = []
    waiting_operation_ids: list[str] = []
    for lot_id in lot_ids:
        pace_by_process = load_lot_process_pace_forecasts(
            session=session,
            lot_id=lot_id,
            pace_min_samples=config.pace_min_samples,
            as_of=as_of,
        )
        bundle = build_internal_lot_forecast_inputs(
            session=session,
            lot_id=lot_id,
            pace_by_process=pace_by_process,
            as_of=as_of,
        )
        waiting_operation_ids.extend(bundle.waiting_operation_ids)
        if bundle.readiness is ForecastReadiness.READY:
            items.extend(bundle.items)

    if waiting_operation_ids:
        actionable_waits = _worker_actionable_waiting_attempt_ids(
            session=session,
            waiting_attempt_ids=waiting_operation_ids,
        )
        return LiveForecastSnapshot(
            plan_id=current_plan.plan_id,
            plan_version=current_plan.version,
            as_of=as_of,
            readiness=ForecastReadiness.WAIT,
            result=None,
            waiting_operation_ids=actionable_waits,
        )

    item_tuple = tuple(items)
    ready_dispatch_provider = build_plan_ready_dispatch_provider(
        session=session,
        plan_id=current_plan.plan_id,
        items=item_tuple,
    )
    calendar = load_work_calendar(session, config.calendar_id)
    schedule_start_time = calendar.next_work_start(as_of)
    schedule = schedule_operations_event_driven(
        items=item_tuple,
        rule=PriorityRule(current_plan.priority_rule),
        static_lot_priorities=(),
        ready_dispatch_provider=ready_dispatch_provider,
        resources=load_active_resources(session),
        calendar=calendar,
        start_time=schedule_start_time,
    )
    result = evaluate_persisted_forecast(
        session=session,
        schedule=schedule,
        lot_ids=lot_ids,
        warning_threshold_minutes=config.warning_threshold_minutes,
    )

    return LiveForecastSnapshot(
        plan_id=current_plan.plan_id,
        plan_version=current_plan.version,
        as_of=as_of,
        readiness=result.readiness,
        result=result,
    )
