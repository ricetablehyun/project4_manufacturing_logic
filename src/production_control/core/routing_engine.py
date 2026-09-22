"""Routing precedence and WIP-buffer release rules."""

from dataclasses import dataclass
from typing import Iterable

from production_control.domain.enums import OperationState


@dataclass(frozen=True, slots=True)
class RoutingOperation:
    """Minimal UnitOperation view required by routing eligibility checks."""

    unit_id: str
    step_seq: int
    process_code: str
    state: OperationState

    def __post_init__(self) -> None:
        if not self.unit_id:
            raise ValueError("unit_id must not be empty")
        if self.step_seq <= 0:
            raise ValueError("step_seq must be greater than 0")
        if not self.process_code:
            raise ValueError("process_code must not be empty")


def predecessors_completed(
    *,
    target: RoutingOperation,
    unit_operations: Iterable[RoutingOperation],
) -> bool:
    """Return whether all earlier normal-routing steps for the Unit are complete.

    Rework is modeled separately as an explicit new attempt/operation path.
    This function only evaluates the normal RoutingStep sequence.
    """

    predecessors = [
        operation
        for operation in unit_operations
        if operation.unit_id == target.unit_id and operation.step_seq < target.step_seq
    ]

    return all(operation.state is OperationState.COMPLETED for operation in predecessors)


def wip_buffer_released(
    *,
    completed_supply_count: int,
    buffer_k: int,
    downstream_started: bool,
) -> bool:
    """Apply the V1 initial WIP Buffer K policy.

    Before the downstream process starts, at least K upstream completions are
    required. Once downstream has started, the initial K threshold no longer
    blocks subsequent flow.
    """

    if completed_supply_count < 0:
        raise ValueError("completed_supply_count must be 0 or greater")
    if buffer_k <= 0:
        raise ValueError("buffer_k must be greater than 0")

    return downstream_started or completed_supply_count >= buffer_k


def downstream_unit_released(
    *,
    upstream_unit_completed: bool,
    completed_supply_count: int,
    buffer_k: int,
    downstream_started: bool,
) -> bool:
    """Return whether one Unit may enter the downstream step."""

    if not upstream_unit_completed:
        return False

    return wip_buffer_released(
        completed_supply_count=completed_supply_count,
        buffer_k=buffer_k,
        downstream_started=downstream_started,
    )
