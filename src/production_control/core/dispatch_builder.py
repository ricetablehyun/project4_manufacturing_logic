"""Build deterministic scheduler dispatch sequences from LOT priority results."""

import collections.abc
from dataclasses import dataclass
from datetime import datetime

from production_control.core import priority_rules
from production_control.domain.enums import OperationState

_STATE_ORDER = {
    OperationState.RUNNING: 0,
    OperationState.WAITING: 1,
    OperationState.HOLD: 2,
}


@dataclass(frozen=True, slots=True)
class OperationDispatchInput:
    """Planning-layer view used only to build a deterministic dispatch sequence."""

    operation_id: str
    lot_id: str
    unit_id: str
    state: OperationState
    eligible_at: datetime

    def __post_init__(self) -> None:
        if not self.operation_id:
            raise ValueError("operation_id must not be empty")
        if not self.lot_id:
            raise ValueError("lot_id must not be empty")
        if not self.unit_id:
            raise ValueError("unit_id must not be empty")
        if self.state is OperationState.COMPLETED:
            raise ValueError("completed operations must not enter dispatch generation")


def _rank_same_lot_operations(
    operations: list[OperationDispatchInput],
) -> list[OperationDispatchInput]:
    """Apply confirmed deterministic tie-break inside one LOT.

    RUNNING -> WAITING -> HOLD -> eligible_at -> unit_id.
    Exact ties preserve caller order.
    """

    return sorted(
        operations,
        key=lambda operation: (
            _STATE_ORDER[operation.state],
            operation.eligible_at,
            operation.unit_id,
        ),
    )


def build_dispatch_sequence(
    *,
    lots: collections.abc.Iterable[priority_rules.LotPriorityInput],
    operations: collections.abc.Iterable[OperationDispatchInput],
    rule: priority_rules.PriorityRule,
) -> tuple[str, ...]:
    """Rank LOTs, then apply the confirmed deterministic same-LOT tie-break."""

    ranked_lots = priority_rules.rank_lots(lots, rule=rule)
    operation_list = list(operations)
    ranked_lot_ids = {lot.lot_id for lot in ranked_lots}

    unknown_lot_ids = {
        operation.lot_id for operation in operation_list if operation.lot_id not in ranked_lot_ids
    }
    if unknown_lot_ids:
        unknown = ", ".join(sorted(unknown_lot_ids))
        raise ValueError(f"operations reference LOTs without priority input: {unknown}")

    by_lot: dict[str, list[OperationDispatchInput]] = {}
    for operation in operation_list:
        by_lot.setdefault(operation.lot_id, []).append(operation)

    sequence: list[str] = []
    for lot in ranked_lots:
        ranked_operations = _rank_same_lot_operations(by_lot.get(lot.lot_id, []))
        sequence.extend(operation.operation_id for operation in ranked_operations)

    return tuple(sequence)
