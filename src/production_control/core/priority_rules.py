"""LOT priority rules used by replanning candidate generation.

The finite scheduler stays policy-neutral. This module only ranks active LOTs
according to the selected dispatching rule.

V1 deadline policy:
- use the next relevant Gate deadline when one exists;
- otherwise use the final due date.

The caller resolves that deadline before creating LotPriorityInput.
"""

from collections.abc import Iterable
from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum
from math import isfinite


class PriorityRule(StrEnum):
    FCFS = "FCFS"
    EDD = "EDD"
    SLACK = "SLACK"
    CR = "CR"


@dataclass(frozen=True, slots=True)
class LotPriorityInput:
    """Priority calculation input for one active LOT."""

    lot_id: str
    release_at: datetime
    deadline: datetime
    remaining_work_minutes: float
    time_until_deadline_minutes: float

    def __post_init__(self) -> None:
        if not self.lot_id:
            raise ValueError("lot_id must not be empty")
        if self.remaining_work_minutes <= 0:
            raise ValueError("remaining_work_minutes must be greater than 0")
        if not isfinite(self.remaining_work_minutes):
            raise ValueError("remaining_work_minutes must be finite")
        if not isfinite(self.time_until_deadline_minutes):
            raise ValueError("time_until_deadline_minutes must be finite")

    @property
    def slack_minutes(self) -> float:
        return self.time_until_deadline_minutes - self.remaining_work_minutes

    @property
    def critical_ratio(self) -> float:
        return self.time_until_deadline_minutes / self.remaining_work_minutes


def resolve_deadline(
    *,
    next_relevant_gate_at: datetime | None,
    final_due_at: datetime,
) -> datetime:
    """Apply the confirmed V1 Gate-first deadline rule."""

    return next_relevant_gate_at if next_relevant_gate_at is not None else final_due_at


def rank_lots(
    lots: Iterable[LotPriorityInput],
    *,
    rule: PriorityRule,
) -> tuple[LotPriorityInput, ...]:
    """Return LOTs from highest to lowest priority.

    Python's sort is stable, so exact metric ties preserve caller order instead
    of inventing an additional production-policy tie-break.
    """

    lot_list = list(lots)

    if rule is PriorityRule.FCFS:
        key = lambda lot: lot.release_at
    elif rule is PriorityRule.EDD:
        key = lambda lot: lot.deadline
    elif rule is PriorityRule.SLACK:
        key = lambda lot: lot.slack_minutes
    elif rule is PriorityRule.CR:
        key = lambda lot: lot.critical_ratio
    else:
        raise ValueError(f"unsupported priority rule: {rule}")

    return tuple(sorted(lot_list, key=key))
