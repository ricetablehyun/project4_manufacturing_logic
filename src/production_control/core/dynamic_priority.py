"""Build dynamic LOT priority inputs at an explicit dispatch decision time."""

from dataclasses import dataclass
from datetime import datetime

from production_control.core.calendar_engine import WorkCalendar
from production_control.core.priority_rules import LotPriorityInput


@dataclass(frozen=True, slots=True)
class DynamicLotPriorityState:
    """State needed to recalculate Slack / CR for one LOT."""

    lot_id: str
    release_at: datetime
    deadline: datetime
    remaining_work_minutes: float

    def __post_init__(self) -> None:
        if not self.lot_id:
            raise ValueError("lot_id must not be empty")
        if self.remaining_work_minutes <= 0:
            raise ValueError("remaining_work_minutes must be greater than 0")


def build_dynamic_priority_input(
    *,
    state: DynamicLotPriorityState,
    decision_time: datetime,
    calendar: WorkCalendar,
) -> LotPriorityInput:
    """Recalculate the WorkCalendar time budget for a dispatch decision point."""

    return LotPriorityInput(
        lot_id=state.lot_id,
        release_at=state.release_at,
        deadline=state.deadline,
        remaining_work_minutes=state.remaining_work_minutes,
        time_until_deadline_minutes=calendar.working_minutes_until(
            decision_time,
            state.deadline,
        ),
    )
