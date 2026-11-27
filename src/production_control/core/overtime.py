"""Weekday overtime for replanning candidates (D078).

The overtime policy is deliberately narrow: a candidate may extend the closing
time of working days by a fixed window (+2 hours by default), weekdays first,
from the replanning moment through the last day that can still help a late
Gate. Opened days whose window no scheduled work uses are dropped, and the KPI
counts only the overtime that work actually uses on each day: from the regular
close to the last resource release inside the window.
"""

from collections.abc import Iterable
from datetime import date, datetime, time, timedelta

from production_control.core.calendar_engine import WorkCalendar
from production_control.core.resource_engine import ResourceAllocation

DEFAULT_OVERTIME_END = time(19, 0)


def overtime_window_days(
    calendar: WorkCalendar,
    *,
    start: datetime,
    through: date,
    extended_end: time = DEFAULT_OVERTIME_END,
) -> tuple[date, ...]:
    """Working days from ``start`` through ``through`` whose overtime window is
    still ahead of ``start`` and not already opened."""

    local = start.astimezone(calendar.tz)
    days: list[date] = []
    day = local.date()
    while day <= through:
        if day.weekday() in calendar.active_weekdays and day not in calendar.overtime_days:
            window_end = datetime.combine(day, extended_end, tzinfo=calendar.tz)
            if local < window_end:
                days.append(day)
        day += timedelta(days=1)
    return tuple(days)


def overtime_used_by_day(
    *,
    calendar: WorkCalendar,
    allocations: Iterable[ResourceAllocation],
    days: Iterable[date],
) -> dict[date, float]:
    """Minutes of each overtime day's window that scheduled resource use needs.

    A day counts from its regular close to the latest allocation end inside the
    window. External lead-time steps hold no resources and never count.
    """

    wanted = set(days)
    if not wanted:
        return {}
    closes = {day: calendar.regular_close(day) for day in wanted}
    used: dict[date, float] = {}
    for allocation in allocations:
        local_end = allocation.end.astimezone(calendar.tz)
        local_start = allocation.start.astimezone(calendar.tz)
        for day in {local_start.date(), local_end.date()} & wanted:
            close = closes[day]
            if local_end <= close:
                continue
            window_close = calendar.closing_time(day)
            last = min(local_end, window_close)
            minutes = (last - close).total_seconds() / 60.0
            if minutes > used.get(day, 0.0):
                used[day] = minutes
    return used
