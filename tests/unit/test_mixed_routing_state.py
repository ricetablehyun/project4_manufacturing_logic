from datetime import datetime
from zoneinfo import ZoneInfo

import pytest

from production_control.core.calendar_engine import WorkCalendar
from production_control.core.external_lead_time import LeadTimeBasis
from production_control.core.mixed_routing_state import (
    ExternalRoutingStepInput,
    build_mixed_routing_state,
)
from production_control.core.pace_scheduler_adapter import UnitPaceSchedulingInput
from production_control.core.slot_engine import ResourceRequirement
from production_control.domain.enums import OperationState

SEOUL = ZoneInfo("Asia/Seoul")


def dt(day: int, hour: int, minute: int = 0) -> datetime:
    return datetime(2026, 10, day, hour, minute, tzinfo=SEOUL)


def unit(
    operation_id: str,
    unit_id: str,
    step_seq: int,
    *,
    lot_id: str = "LOT-A",
    release_at: datetime | None = None,
) -> UnitPaceSchedulingInput:
    return UnitPaceSchedulingInput(
        operation_id=operation_id,
        lot_id=lot_id,
        unit_id=unit_id,
        step_seq=step_seq,
        process_code=f"STEP_{step_seq}",
        state=OperationState.WAITING,
        eligible_at=dt(5, 9),
        release_at=release_at or dt(5, 9),
        requirements=(ResourceRequirement("WORKER_POOL"),),
    )


def external(
    *,
    step_seq: int = 2,
    ready_at: datetime | None = None,
    lead_minutes: float = 120,
    basis: LeadTimeBasis = LeadTimeBasis.WORKING,
    lot_id: str = "LOT-A",
) -> ExternalRoutingStepInput:
    return ExternalRoutingStepInput(
        lot_id=lot_id,
        step_seq=step_seq,
        process_code="EXTERNAL_FEED_BONDING",
        ready_at=ready_at or dt(5, 10),
        lead_minutes=lead_minutes,
        basis=basis,
    )


def test_external_step_pushes_only_downstream_internal_release() -> None:
    state = build_mixed_routing_state(
        internal_units=(
            unit("U1-S1", "U1", 1),
            unit("U1-S3", "U1", 3),
        ),
        external_steps=(external(),),
        calendar=WorkCalendar(),
    )

    by_id = {item.operation_id: item for item in state.internal_units}
    assert by_id["U1-S1"].release_at == dt(5, 9)
    assert by_id["U1-S3"].release_at == dt(5, 12)


def test_external_step_is_one_lot_barrier_for_all_downstream_units() -> None:
    state = build_mixed_routing_state(
        internal_units=(
            unit("U1-S3", "U1", 3),
            unit("U2-S3", "U2", 3),
        ),
        external_steps=(external(lead_minutes=90),),
        calendar=WorkCalendar(),
    )

    assert {
        item.release_at
        for item in state.internal_units
    } == {dt(5, 11, 30)}


def test_existing_later_release_is_not_moved_backward() -> None:
    state = build_mixed_routing_state(
        internal_units=(
            unit("U1-S3", "U1", 3, release_at=dt(5, 14)),
        ),
        external_steps=(external(lead_minutes=120),),
        calendar=WorkCalendar(),
    )

    assert state.internal_units[0].release_at == dt(5, 14)


def test_working_external_barrier_skips_weekend() -> None:
    state = build_mixed_routing_state(
        internal_units=(unit("U1-S3", "U1", 3),),
        external_steps=(
            external(
                ready_at=dt(9, 16, 30),
                lead_minutes=90,
                basis=LeadTimeBasis.WORKING,
            ),
        ),
        calendar=WorkCalendar(),
    )

    barrier = state.external_barriers[0]
    assert barrier.result.end == dt(12, 10)
    assert state.internal_units[0].release_at == dt(12, 10)


def test_calendar_external_barrier_counts_closed_time() -> None:
    state = build_mixed_routing_state(
        internal_units=(unit("U1-S3", "U1", 3),),
        external_steps=(
            external(
                ready_at=dt(9, 16, 30),
                lead_minutes=90,
                basis=LeadTimeBasis.CALENDAR,
            ),
        ),
        calendar=WorkCalendar(),
    )

    assert state.external_barriers[0].result.end == dt(9, 18)
    assert state.internal_units[0].release_at == dt(9, 18)


def test_external_barrier_does_not_cross_lot_boundary() -> None:
    state = build_mixed_routing_state(
        internal_units=(
            unit("A-S3", "U1", 3, lot_id="LOT-A"),
            unit("B-S3", "U1", 3, lot_id="LOT-B"),
        ),
        external_steps=(external(lot_id="LOT-A"),),
        calendar=WorkCalendar(),
    )

    by_id = {item.operation_id: item for item in state.internal_units}
    assert by_id["A-S3"].release_at == dt(5, 12)
    assert by_id["B-S3"].release_at == dt(5, 9)


def test_latest_prior_external_barrier_controls_release() -> None:
    state = build_mixed_routing_state(
        internal_units=(unit("U1-S5", "U1", 5),),
        external_steps=(
            external(step_seq=2, ready_at=dt(5, 9), lead_minutes=60),
            ExternalRoutingStepInput(
                lot_id="LOT-A",
                step_seq=4,
                process_code="EXTERNAL_2",
                ready_at=dt(5, 13),
                lead_minutes=60,
                basis=LeadTimeBasis.WORKING,
            ),
        ),
        calendar=WorkCalendar(),
    )

    assert state.internal_units[0].release_at == dt(5, 14)


def test_duplicate_external_step_seq_in_same_lot_is_rejected() -> None:
    with pytest.raises(ValueError):
        build_mixed_routing_state(
            internal_units=(unit("U1-S3", "U1", 3),),
            external_steps=(
                external(step_seq=2),
                ExternalRoutingStepInput(
                    lot_id="LOT-A",
                    step_seq=2,
                    process_code="OTHER_EXTERNAL",
                    ready_at=dt(5, 10),
                    lead_minutes=60,
                    basis=LeadTimeBasis.WORKING,
                ),
            ),
            calendar=WorkCalendar(),
        )
