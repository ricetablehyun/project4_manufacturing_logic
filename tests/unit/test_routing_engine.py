import pytest

from production_control.core.routing_engine import (
    RoutingOperation,
    downstream_unit_released,
    predecessors_completed,
    wip_buffer_released,
)
from production_control.domain.enums import OperationState


def operation(step: int, state: OperationState, unit: str = "U01") -> RoutingOperation:
    return RoutingOperation(
        unit_id=unit,
        step_seq=step,
        process_code=f"STEP_{step}",
        state=state,
    )


def test_first_routing_step_has_no_predecessor_block() -> None:
    target = operation(1, OperationState.WAITING)

    assert predecessors_completed(target=target, unit_operations=[target])


def test_next_step_is_blocked_until_previous_step_completes() -> None:
    previous = operation(1, OperationState.RUNNING)
    target = operation(2, OperationState.WAITING)

    assert not predecessors_completed(
        target=target,
        unit_operations=[previous, target],
    )


def test_next_step_is_released_after_previous_step_completes() -> None:
    previous = operation(1, OperationState.COMPLETED)
    target = operation(2, OperationState.WAITING)

    assert predecessors_completed(
        target=target,
        unit_operations=[previous, target],
    )


def test_all_earlier_steps_must_be_complete() -> None:
    operations = [
        operation(1, OperationState.COMPLETED),
        operation(2, OperationState.HOLD),
        operation(3, OperationState.WAITING),
    ]

    assert not predecessors_completed(
        target=operations[2],
        unit_operations=operations,
    )


def test_other_unit_state_does_not_block_target_unit() -> None:
    target_previous = operation(1, OperationState.COMPLETED, unit="U01")
    target = operation(2, OperationState.WAITING, unit="U01")
    other_unit = operation(1, OperationState.RUNNING, unit="U02")

    assert predecessors_completed(
        target=target,
        unit_operations=[target_previous, target, other_unit],
    )


def test_initial_downstream_release_requires_k_completed_units() -> None:
    assert not wip_buffer_released(
        completed_supply_count=1,
        buffer_k=2,
        downstream_started=False,
    )
    assert wip_buffer_released(
        completed_supply_count=2,
        buffer_k=2,
        downstream_started=False,
    )


def test_after_downstream_starts_initial_k_no_longer_blocks_flow() -> None:
    assert wip_buffer_released(
        completed_supply_count=1,
        buffer_k=2,
        downstream_started=True,
    )


def test_unit_itself_must_have_completed_upstream_step() -> None:
    assert not downstream_unit_released(
        upstream_unit_completed=False,
        completed_supply_count=3,
        buffer_k=2,
        downstream_started=True,
    )


def test_completed_unit_is_released_when_buffer_condition_is_met() -> None:
    assert downstream_unit_released(
        upstream_unit_completed=True,
        completed_supply_count=2,
        buffer_k=2,
        downstream_started=False,
    )


def test_invalid_buffer_values_are_rejected() -> None:
    with pytest.raises(ValueError):
        wip_buffer_released(
            completed_supply_count=-1,
            buffer_k=2,
            downstream_started=False,
        )

    with pytest.raises(ValueError):
        wip_buffer_released(
            completed_supply_count=1,
            buffer_k=0,
            downstream_started=False,
        )
