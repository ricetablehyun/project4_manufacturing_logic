"""LOT-level external-process lead-time calculation.

External production-team work is modeled as LOT_LEAD_TIME rather than an
internal finite-capacity Resource operation. RoutingStep chooses whether the
lead consumes WorkCalendar time or ordinary calendar time.
"""

from dataclasses import dataclass
from datetime import datetime, timedelta
from enum import StrEnum
from math import isfinite

from production_control.core.calendar_engine import WorkCalendar


class LeadTimeBasis(StrEnum):
    WORKING = "WORKING"
    CALENDAR = "CALENDAR"


@dataclass(frozen=True, slots=True)
class LotLeadTimeSpec:
    """Input for one external LOT-level routing step."""

    lot_id: str
    process_code: str
    ready_at: datetime
    lead_minutes: float
    basis: LeadTimeBasis

    def __post_init__(self) -> None:
        if not self.lot_id:
            raise ValueError("lot_id must not be empty")
        if not self.process_code:
            raise ValueError("process_code must not be empty")
        if self.ready_at.tzinfo is None or self.ready_at.utcoffset() is None:
            raise ValueError("ready_at must be timezone-aware")
        if self.lead_minutes <= 0 or not isfinite(self.lead_minutes):
            raise ValueError("lead_minutes must be finite and greater than 0")


@dataclass(frozen=True, slots=True)
class LotLeadTimeResult:
    """Forecast interval for one external LOT-level routing step."""

    lot_id: str
    process_code: str
    start: datetime
    end: datetime
    basis: LeadTimeBasis
    lead_minutes: float


def schedule_lot_lead_time(
    *,
    spec: LotLeadTimeSpec,
    calendar: WorkCalendar,
) -> LotLeadTimeResult:
    """Calculate external-step finish without consuming internal Resources."""

    if spec.basis is LeadTimeBasis.WORKING:
        start = calendar.next_work_start(spec.ready_at)
        end = calendar.add_working_minutes(spec.ready_at, spec.lead_minutes)
    elif spec.basis is LeadTimeBasis.CALENDAR:
        start = spec.ready_at
        end = spec.ready_at + timedelta(minutes=spec.lead_minutes)
    else:
        raise ValueError(f"unsupported lead-time basis: {spec.basis}")

    return LotLeadTimeResult(
        lot_id=spec.lot_id,
        process_code=spec.process_code,
        start=start,
        end=end,
        basis=spec.basis,
        lead_minutes=spec.lead_minutes,
    )
