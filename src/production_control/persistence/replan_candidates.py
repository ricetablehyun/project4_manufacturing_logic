"""Build transient replanning candidates from current persisted production state.

D056 keeps candidate plans outside persistence. The latest approved plan remains
current until a manager explicitly approves one candidate through a separate
application boundary.
"""

from collections.abc import Iterable
from dataclasses import dataclass
from datetime import datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from production_control.core.candidate_evaluator import (
    CandidateKPI,
    PriorityRankSnapshot,
    count_priority_rank_changes,
)
from production_control.core.dynamic_priority import (
    DynamicLotPriorityState,
    build_dynamic_priority_input,
)
from production_control.core.event_scheduler import (
    DynamicPriorityProvider,
    EventDispatchInput,
    schedule_operations_event_driven,
)
from production_control.core.finite_scheduler import (
    OperationSpec,
    ScheduledOperation,
    ScheduleResult,
)
from production_control.core.pace_scheduler_adapter import ForecastReadiness
from production_control.core.priority_rules import (
    LotPriorityInput,
    PriorityRule,
    resolve_deadline,
)
from production_control.core.replan_policy import ReplanAction
from production_control.core.risk_engine import RiskLevel
from production_control.persistence.forecast_input_bundle import (
    build_internal_lot_forecast_inputs,
)
from production_control.persistence.forecast_result import (
    PersistedForecastResult,
    evaluate_persisted_forecast,
)
from production_control.persistence.live_forecast import (
    LiveForecastConfig,
    build_live_forecast,
)
from production_control.persistence.mappers import load_active_resources, load_work_calendar
from production_control.persistence.models import InspectionGateRow, LotRow
from production_control.persistence.pace_snapshot import load_lot_process_pace_forecasts
from production_control.persistence.plan_dispatch import (
    PlanTaskPriority,
    load_plan_task_priorities,
)
from production_control.persistence.plan_lifecycle import load_current_approved_plan
from production_control.persistence.replan_orchestration import (
    orchestrate_persisted_forecast,
)


@dataclass(frozen=True, slots=True)
class ReplanCandidateTask:
    """One transient LOT x RoutingStep task in a candidate plan."""

    lot_id: str
    routing_step_id: str
    target_start: datetime
    target_end: datetime
    target_qty: int
    priority_rank: int


@dataclass(frozen=True, slots=True)
class PersistedReplanCandidate:
    candidate_id: str
    rule: PriorityRule
    kpi: CandidateKPI
    tasks: tuple[ReplanCandidateTask, ...]


@dataclass(frozen=True, slots=True)
class PersistedReplanCandidateSnapshot:
    parent_plan_id: str
    parent_plan_version: int
    as_of: datetime
    risk_level: RiskLevel
    action: ReplanAction
    recommended_candidate_id: str | None
    requires_manager_approval: bool
    candidates: tuple[PersistedReplanCandidate, ...]


@dataclass(frozen=True, slots=True)
class _LotPriorityState:
    lot_id: str
    release_at: datetime
    deadline: datetime


def _load_priority_states(
    *,
    session: Session,
    lot_ids: tuple[str, ...],
) -> dict[str, _LotPriorityState]:
    states: dict[str, _LotPriorityState] = {}
    for lot_id in lot_ids:
        lot = session.get(LotRow, lot_id)
        if lot is None:
            raise ValueError(f"unknown lot_id: {lot_id}")

        next_gate = session.scalar(
            select(InspectionGateRow)
            .where(
                InspectionGateRow.lot_id == lot_id,
                InspectionGateRow.completed_at.is_(None),
            )
            .order_by(InspectionGateRow.planned_at, InspectionGateRow.gate_id)
            .limit(1)
        )
        states[lot_id] = _LotPriorityState(
            lot_id=lot_id,
            release_at=lot.release_at,
            deadline=resolve_deadline(
                next_relevant_gate_at=(
                    None if next_gate is None else next_gate.planned_at
                ),
                final_due_at=lot.due_at,
            ),
        )
    return states


def _load_candidate_items(
    *,
    session: Session,
    lot_ids: tuple[str, ...],
    as_of: datetime,
    config: LiveForecastConfig,
) -> tuple[EventDispatchInput, ...]:
    items: list[EventDispatchInput] = []
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
        unresolved = ", ".join(sorted(set(waiting_operation_ids)))
        raise ValueError(
            "replanning requires READY Live Forecast; unresolved operations: "
            f"{unresolved}"
        )

    return tuple(items)


def _remaining_minutes_by_lot(
    operations: Iterable[OperationSpec],
) -> dict[str, float]:
    remaining: dict[str, float] = {}
    for operation in operations:
        remaining[operation.lot_id] = (
            remaining.get(operation.lot_id, 0.0) + operation.duration_minutes
        )
    return remaining


def _static_priority_inputs(
    *,
    lot_order: tuple[str, ...],
    states: dict[str, _LotPriorityState],
    items: tuple[EventDispatchInput, ...],
    as_of: datetime,
    calendar,
) -> tuple[LotPriorityInput, ...]:
    remaining = _remaining_minutes_by_lot(item.operation for item in items)
    result: list[LotPriorityInput] = []
    for lot_id in lot_order:
        remaining_minutes = remaining.get(lot_id)
        if remaining_minutes is None or remaining_minutes <= 0:
            continue
        state = states[lot_id]
        result.append(
            LotPriorityInput(
                lot_id=lot_id,
                release_at=state.release_at,
                deadline=state.deadline,
                remaining_work_minutes=remaining_minutes,
                time_until_deadline_minutes=calendar.working_minutes_until(
                    as_of,
                    state.deadline,
                ),
            )
        )
    return tuple(result)


def _dynamic_priority_provider(
    *,
    lot_order: tuple[str, ...],
    states: dict[str, _LotPriorityState],
    calendar,
) -> DynamicPriorityProvider:
    def provider(
        decision_time: datetime,
        pending_operations: tuple[OperationSpec, ...],
        scheduled_operations: tuple[ScheduledOperation, ...],
    ) -> tuple[LotPriorityInput, ...]:
        remaining = _remaining_minutes_by_lot(pending_operations)
        for operation in scheduled_operations:
            if operation.end <= decision_time:
                continue
            residual_minutes = calendar.working_minutes_between(
                decision_time,
                operation.end,
            )
            if residual_minutes > 0:
                remaining[operation.lot_id] = (
                    remaining.get(operation.lot_id, 0.0) + residual_minutes
                )

        result: list[LotPriorityInput] = []
        for lot_id in lot_order:
            remaining_minutes = remaining.get(lot_id)
            if remaining_minutes is None or remaining_minutes <= 0:
                continue
            state = states[lot_id]
            result.append(
                build_dynamic_priority_input(
                    state=DynamicLotPriorityState(
                        lot_id=lot_id,
                        release_at=state.release_at,
                        deadline=state.deadline,
                        remaining_work_minutes=remaining_minutes,
                    ),
                    decision_time=decision_time,
                    calendar=calendar,
                )
            )
        return tuple(result)

    return provider


def _candidate_tasks(
    *,
    session: Session,
    schedule: ScheduleResult,
    parent_priorities: tuple[PlanTaskPriority, ...],
) -> tuple[tuple[ReplanCandidateTask, ...], int]:
    priority_by_key = {
        priority.operation_key: priority
        for priority in parent_priorities
    }
    grouped: dict[tuple[str, int, str], list] = {}
    dispatch_order: list[tuple[str, int, str]] = []

    for operation in schedule.operations:
        key = (operation.lot_id, operation.step_seq, operation.process_code)
        if key not in priority_by_key:
            raise ValueError(
                "candidate operation has no matching task in the current approved plan: "
                f"{operation.operation_id} / {key}"
            )
        if key not in grouped:
            grouped[key] = []
            dispatch_order.append(key)
        grouped[key].append(operation)

    active_parent_priorities = sorted(
        (priority_by_key[key] for key in dispatch_order),
        key=lambda item: (item.priority_rank, item.technical_order),
    )
    rank_slots = [item.priority_rank for item in active_parent_priorities]
    candidate_rank_by_key = {
        key: rank_slots[index]
        for index, key in enumerate(dispatch_order)
    }

    approved_snapshots: list[PriorityRankSnapshot] = []
    candidate_snapshots: list[PriorityRankSnapshot] = []
    process_keys = {(key[0], key[2]) for key in dispatch_order}
    if len(process_keys) != len(dispatch_order):
        raise ValueError(
            "candidate change_count requires one routing step per LOT x process_code"
        )

    tasks: list[ReplanCandidateTask] = []
    for key in dispatch_order:
        lot_id, _step_seq, process_code = key
        parent = priority_by_key[key]
        operations = grouped[key]
        lot = session.get(LotRow, lot_id)
        if lot is None:
            raise ValueError(f"unknown lot_id: {lot_id}")

        candidate_rank = candidate_rank_by_key[key]
        tasks.append(
            ReplanCandidateTask(
                lot_id=lot_id,
                routing_step_id=parent.routing_step_id,
                target_start=min(operation.start for operation in operations),
                target_end=max(operation.end for operation in operations),
                target_qty=lot.quantity,
                priority_rank=candidate_rank,
            )
        )

        # D024 permits the Frozen Horizon to be released for URGENT immediate
        # replanning. D056 only builds candidates after that URGENT boundary,
        # so the active candidate comparison set is intentionally unfrozen.
        approved_snapshots.append(
            PriorityRankSnapshot(
                lot_id=lot_id,
                process_code=process_code,
                priority_rank=parent.priority_rank,
                frozen=False,
            )
        )
        candidate_snapshots.append(
            PriorityRankSnapshot(
                lot_id=lot_id,
                process_code=process_code,
                priority_rank=candidate_rank,
                frozen=False,
            )
        )

    change_count = count_priority_rank_changes(
        approved=approved_snapshots,
        candidate=candidate_snapshots,
    )
    tasks.sort(key=lambda task: (task.priority_rank, task.lot_id, task.routing_step_id))
    return tuple(tasks), change_count


def _candidate_kpi(
    *,
    candidate_id: str,
    forecast: PersistedForecastResult,
    change_count: int,
) -> CandidateKPI:
    late_lot_ids: set[str] = set()
    total_tardiness_minutes = 0.0
    for gate in forecast.gate_forecasts:
        tardiness = max(-gate.risk.slack_minutes, 0.0)
        if tardiness > 0:
            late_lot_ids.add(gate.lot_id)
        total_tardiness_minutes += tardiness

    return CandidateKPI(
        candidate_id=candidate_id,
        late_lot_count=len(late_lot_ids),
        total_tardiness_minutes=total_tardiness_minutes,
        # The current scheduler only uses the normal WorkCalendar. It cannot
        # create overtime until a later CalendarException slice supplies it.
        overtime_minutes=0.0,
        change_count=change_count,
    )


def build_replan_candidates(
    *,
    session: Session,
    as_of: datetime,
    config: LiveForecastConfig,
) -> PersistedReplanCandidateSnapshot:
    """Build transient D056 candidates without persisting SchedulePlan rows."""

    live = build_live_forecast(
        session=session,
        as_of=as_of,
        config=config,
    )
    if live.readiness is not ForecastReadiness.READY or live.result is None:
        unresolved = ", ".join(live.waiting_operation_ids) or "unknown Forecast inputs"
        raise ValueError(
            "replanning requires READY Live Forecast; unresolved: "
            f"{unresolved}"
        )

    boundary = orchestrate_persisted_forecast(forecast=live.result)
    if boundary.action is not ReplanAction.GENERATE_CANDIDATES:
        return PersistedReplanCandidateSnapshot(
            parent_plan_id=live.plan_id,
            parent_plan_version=live.plan_version,
            as_of=as_of,
            risk_level=boundary.risk_level,
            action=boundary.action,
            recommended_candidate_id=None,
            requires_manager_approval=False,
            candidates=(),
        )

    current_plan = load_current_approved_plan(session=session)
    parent_priorities = load_plan_task_priorities(
        session=session,
        plan_id=current_plan.plan_id,
    )
    lot_order = tuple(
        dict.fromkeys(priority.lot_id for priority in parent_priorities)
    )
    items = _load_candidate_items(
        session=session,
        lot_ids=lot_order,
        as_of=as_of,
        config=config,
    )
    calendar = load_work_calendar(session, config.calendar_id)
    resources = load_active_resources(session)
    states = _load_priority_states(session=session, lot_ids=lot_order)
    static_priorities = _static_priority_inputs(
        lot_order=lot_order,
        states=states,
        items=items,
        as_of=as_of,
        calendar=calendar,
    )
    dynamic_provider = _dynamic_priority_provider(
        lot_order=lot_order,
        states=states,
        calendar=calendar,
    )

    built: dict[PriorityRule, PersistedReplanCandidate] = {}

    def candidate_builder(rule: PriorityRule) -> CandidateKPI:
        schedule = schedule_operations_event_driven(
            items=items,
            rule=rule,
            static_lot_priorities=static_priorities,
            dynamic_priority_provider=(
                dynamic_provider
                if rule in (PriorityRule.SLACK, PriorityRule.CR)
                else None
            ),
            resources=resources,
            calendar=calendar,
            start_time=as_of,
        )
        candidate_forecast = evaluate_persisted_forecast(
            session=session,
            schedule=schedule,
            lot_ids=lot_order,
            warning_threshold_minutes=config.warning_threshold_minutes,
        )
        if candidate_forecast.readiness is not ForecastReadiness.READY:
            unresolved = ", ".join(candidate_forecast.missing_gate_ids)
            raise ValueError(
                "candidate forecast is not READY; unresolved Gates: "
                f"{unresolved}"
            )

        tasks, change_count = _candidate_tasks(
            session=session,
            schedule=schedule,
            parent_priorities=parent_priorities,
        )
        kpi = _candidate_kpi(
            candidate_id=rule.value,
            forecast=candidate_forecast,
            change_count=change_count,
        )
        built[rule] = PersistedReplanCandidate(
            candidate_id=rule.value,
            rule=rule,
            kpi=kpi,
            tasks=tasks,
        )
        return kpi

    orchestration = orchestrate_persisted_forecast(
        forecast=live.result,
        candidate_builder=candidate_builder,
    )
    candidates = tuple(
        built[candidate.rule]
        for candidate in orchestration.candidates
    )

    return PersistedReplanCandidateSnapshot(
        parent_plan_id=live.plan_id,
        parent_plan_version=live.plan_version,
        as_of=as_of,
        risk_level=orchestration.risk_level,
        action=orchestration.action,
        recommended_candidate_id=orchestration.recommended_candidate_id,
        requires_manager_approval=orchestration.requires_manager_approval,
        candidates=candidates,
    )
