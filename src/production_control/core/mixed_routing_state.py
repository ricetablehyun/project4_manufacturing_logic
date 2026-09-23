"""Build mixed internal/external routing state for Forecast scheduling.

The external team remains a LOT-level lead-time barrier, not an internal
finite-capacity Resource. This builder takes an externally known ready_at,
calculates its LOT_LEAD_TIME completion, and pushes that completion time into
release_at for later internal Unit operations.

It deliberately does not guess when an external step becomes ready. That
timestamp must come from execution state or an upstream scheduling result.
"""

from dataclasses import dataclass, replace
from datetime import datetime

from production_control.core.calendar_engine import WorkCalendar
from production_control.core.external_lead_time import (
    LeadTimeBasis,
    LotLeadTimeResult,
    LotLeadTimeSpec,
    schedule_lot_lead_time,
)
from production_control.core.pace_scheduler_adapter import UnitPaceSchedulingInput


@dataclass(frozen=True, slots=True)
class ExternalRoutingStepInput:
    """One LOT-level external step embedded in a Routing sequence."""

    lot_id: str
    step_seq: int
    process_code: str
    ready_at: datetime
    lead_minutes: float
    basis: LeadTimeBasis

    def __post_init__(self) -> None:
        if not self.lot_id:
            raise ValueError("lot_id must not be empty")
        if self.step_seq <= 0:
            raise ValueError("step_seq must be greater than 0")
        if not self.process_code:
            raise ValueError("process_code must not be empty")


@dataclass(frozen=True, slots=True)
class ExternalRoutingBarrier:
    """Calculated LOT-level release barrier created by an external step."""

    lot_id: str
    step_seq: int
    process_code: str
    result: LotLeadTimeResult


@dataclass(frozen=True, slots=True)
class MixedRoutingState:
    """Internal Unit inputs plus calculated external release barriers."""

    internal_units: tuple[UnitPaceSchedulingInput, ...]
    external_barriers: tuple[ExternalRoutingBarrier, ...]


def _validate_external_steps(
    steps: tuple[ExternalRoutingStepInput, ...],
) -> None:
    keys = [(step.lot_id, step.step_seq) for step in steps]
    if len(keys) != len(set(keys)):
        raise ValueError("LOT + external step_seq must be unique")


def _validate_internal_units(
    units: tuple[UnitPaceSchedulingInput, ...],
) -> None:
    routing_keys = [
        (unit.lot_id, unit.unit_id, unit.step_seq)
        for unit in units
    ]
    if len(routing_keys) != len(set(routing_keys)):
        raise ValueError("LOT + Unit + step_seq must be unique")


def build_mixed_routing_state(
    *,
    internal_units: tuple[UnitPaceSchedulingInput, ...],
    external_steps: tuple[ExternalRoutingStepInput, ...],
    calendar: WorkCalendar,
) -> MixedRoutingState:
    """Apply external LOT lead-time completion as downstream release constraints."""

    _validate_internal_units(internal_units)
    _validate_external_steps(external_steps)

    barriers = tuple(
        ExternalRoutingBarrier(
            lot_id=step.lot_id,
            step_seq=step.step_seq,
            process_code=step.process_code,
            result=schedule_lot_lead_time(
                spec=LotLeadTimeSpec(
                    lot_id=step.lot_id,
                    process_code=step.process_code,
                    ready_at=step.ready_at,
                    lead_minutes=step.lead_minutes,
                    basis=step.basis,
                ),
                calendar=calendar,
            ),
        )
        for step in sorted(
            external_steps,
            key=lambda candidate: (
                candidate.lot_id,
                candidate.step_seq,
                candidate.process_code,
            ),
        )
    )

    constrained_units: list[UnitPaceSchedulingInput] = []
    for unit in internal_units:
        prior_external_ends = [
            barrier.result.end
            for barrier in barriers
            if barrier.lot_id == unit.lot_id
            and barrier.step_seq < unit.step_seq
        ]
        if not prior_external_ends:
            constrained_units.append(unit)
            continue

        constrained_units.append(
            replace(
                unit,
                release_at=max(unit.release_at, max(prior_external_ends)),
            )
        )

    return MixedRoutingState(
        internal_units=tuple(constrained_units),
        external_barriers=barriers,
    )
