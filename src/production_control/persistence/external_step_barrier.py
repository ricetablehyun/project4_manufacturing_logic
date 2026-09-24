"""Persist and apply LOT-level external-step Forecast barriers.

D050/D051 keep external production-team work out of UnitOperation. The manager
maintains a LOT x RoutingStep expected finish timestamp instead. Forecast uses
actual finish when known, otherwise the current expected finish.
"""

from collections.abc import Mapping
from dataclasses import dataclass, replace
from datetime import datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from production_control.core.event_scheduler import EventDispatchInput
from production_control.core.pace_estimator import PaceForecast
from production_control.core.pace_scheduler_adapter import (
    ForecastReadiness,
    UnitPaceSignal,
)
from production_control.persistence.forecast_input_bundle import (
    PersistedForecastInputBundle,
    build_internal_lot_forecast_inputs,
)
from production_control.persistence.models import (
    LotExternalStepRow,
    LotRow,
    ProcessRow,
    RoutingRow,
    RoutingStepRow,
)


@dataclass(frozen=True, slots=True)
class ExternalStepBarrier:
    lot_id: str
    routing_step_id: str
    process_code: str
    step_seq: int
    finish_at: datetime
    finish_basis: str
    status: str


@dataclass(frozen=True, slots=True)
class FullLotForecastInputBundle:
    readiness: ForecastReadiness
    items: tuple[EventDispatchInput, ...]
    waiting_operation_ids: tuple[str, ...]
    missing_external_step_ids: tuple[str, ...]
    signals: tuple[UnitPaceSignal, ...]
    external_barriers: tuple[ExternalStepBarrier, ...]


def _load_active_routing(
    session: Session,
    *,
    product_id: str,
) -> RoutingRow:
    rows = session.scalars(
        select(RoutingRow)
        .where(
            RoutingRow.product_id == product_id,
            RoutingRow.active.is_(True),
        )
        .order_by(RoutingRow.version)
    ).all()
    if len(rows) != 1:
        raise ValueError(
            "full Forecast requires exactly one active Routing for product "
            f"{product_id}; found {len(rows)}"
        )
    return rows[0]


def _load_external_steps(
    session: Session,
    *,
    routing_id: str,
) -> tuple[tuple[RoutingStepRow, ProcessRow], ...]:
    rows = session.execute(
        select(RoutingStepRow, ProcessRow)
        .join(ProcessRow, RoutingStepRow.process_id == ProcessRow.process_id)
        .where(
            RoutingStepRow.routing_id == routing_id,
            RoutingStepRow.duration_mode == "LOT_LEAD_TIME",
        )
        .order_by(RoutingStepRow.seq_no, RoutingStepRow.routing_step_id)
    ).all()
    return tuple(rows)


def load_lot_external_barriers(
    *,
    session: Session,
    lot_id: str,
) -> tuple[tuple[ExternalStepBarrier, ...], tuple[str, ...]]:
    """Return resolved external barriers and unresolved RoutingStep ids."""

    lot = session.get(LotRow, lot_id)
    if lot is None:
        raise ValueError(f"unknown lot_id: {lot_id}")

    routing = _load_active_routing(
        session,
        product_id=lot.product_id,
    )
    barriers: list[ExternalStepBarrier] = []
    missing: list[str] = []

    for step, process in _load_external_steps(
        session,
        routing_id=routing.routing_id,
    ):
        state = session.get(
            LotExternalStepRow,
            (lot_id, step.routing_step_id),
        )
        if state is None:
            missing.append(step.routing_step_id)
            continue

        if state.actual_finish_at is not None:
            finish_at = state.actual_finish_at
            finish_basis = "ACTUAL"
        elif state.expected_finish_at is not None:
            finish_at = state.expected_finish_at
            finish_basis = "EXPECTED"
        else:
            missing.append(step.routing_step_id)
            continue

        barriers.append(
            ExternalStepBarrier(
                lot_id=lot_id,
                routing_step_id=step.routing_step_id,
                process_code=process.process_code,
                step_seq=step.seq_no,
                finish_at=finish_at,
                finish_basis=finish_basis,
                status=state.status,
            )
        )

    return tuple(barriers), tuple(missing)


def _apply_external_barriers(
    *,
    items: tuple[EventDispatchInput, ...],
    barriers: tuple[ExternalStepBarrier, ...],
) -> tuple[EventDispatchInput, ...]:
    adjusted: list[EventDispatchInput] = []

    for item in items:
        applicable = [
            barrier.finish_at
            for barrier in barriers
            if item.operation.step_seq > barrier.step_seq
        ]
        if not applicable:
            adjusted.append(item)
            continue

        release_at = max(item.operation.release_at, *applicable)
        adjusted.append(
            replace(
                item,
                operation=replace(
                    item.operation,
                    release_at=release_at,
                ),
            )
        )

    return tuple(adjusted)


def save_lot_external_step_state(
    *,
    session: Session,
    lot_id: str,
    routing_step_id: str,
    expected_finish_at: datetime | None,
    actual_finish_at: datetime | None,
    status: str,
    updated_at: datetime,
) -> LotExternalStepRow:
    """Insert or update one manager-maintained LOT external-step state."""

    if not status:
        raise ValueError("status must not be empty")
    for name, value in (
        ("expected_finish_at", expected_finish_at),
        ("actual_finish_at", actual_finish_at),
        ("updated_at", updated_at),
    ):
        if value is not None and (
            value.tzinfo is None or value.utcoffset() is None
        ):
            raise ValueError(f"{name} must be timezone-aware")

    lot = session.get(LotRow, lot_id)
    if lot is None:
        raise ValueError(f"unknown lot_id: {lot_id}")
    routing = _load_active_routing(
        session,
        product_id=lot.product_id,
    )
    step = session.get(RoutingStepRow, routing_step_id)
    if step is None:
        raise ValueError(f"unknown routing_step_id: {routing_step_id}")
    if step.routing_id != routing.routing_id:
        raise ValueError(
            "external step does not belong to LOT active Routing: "
            f"{routing_step_id}"
        )
    if step.duration_mode != "LOT_LEAD_TIME":
        raise ValueError(
            "LotExternalStep requires LOT_LEAD_TIME RoutingStep: "
            f"{routing_step_id}"
        )

    row = session.get(
        LotExternalStepRow,
        (lot_id, routing_step_id),
    )
    if row is None:
        row = LotExternalStepRow(
            lot_id=lot_id,
            routing_step_id=routing_step_id,
            expected_finish_at=expected_finish_at,
            actual_finish_at=actual_finish_at,
            status=status,
            updated_at=updated_at,
        )
        session.add(row)
    else:
        row.expected_finish_at = expected_finish_at
        row.actual_finish_at = actual_finish_at
        row.status = status
        row.updated_at = updated_at

    session.commit()
    return row


def build_full_lot_forecast_inputs(
    *,
    session: Session,
    lot_id: str,
    pace_by_process: Mapping[str, PaceForecast],
) -> FullLotForecastInputBundle:
    """Build scheduler inputs with external LOT-level barriers applied."""

    internal: PersistedForecastInputBundle = build_internal_lot_forecast_inputs(
        session=session,
        lot_id=lot_id,
        pace_by_process=pace_by_process,
    )
    barriers, missing = load_lot_external_barriers(
        session=session,
        lot_id=lot_id,
    )

    if (
        internal.readiness is ForecastReadiness.WAIT
        or missing
    ):
        return FullLotForecastInputBundle(
            readiness=ForecastReadiness.WAIT,
            items=(),
            waiting_operation_ids=internal.waiting_operation_ids,
            missing_external_step_ids=missing,
            signals=internal.signals,
            external_barriers=barriers,
        )

    return FullLotForecastInputBundle(
        readiness=ForecastReadiness.READY,
        items=_apply_external_barriers(
            items=internal.items,
            barriers=barriers,
        ),
        waiting_operation_ids=(),
        missing_external_step_ids=(),
        signals=internal.signals,
        external_barriers=barriers,
    )
