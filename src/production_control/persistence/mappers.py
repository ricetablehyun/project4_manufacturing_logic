"""Thin persistence-to-core mappers for confirmed reference data."""

from datetime import time

from sqlalchemy import select
from sqlalchemy.orm import Session

from production_control.core.calendar_engine import WorkCalendar
from production_control.core.resource_engine import Resource
from production_control.persistence.models import ResourceRow, WorkCalendarRow


def load_active_resources(session: Session) -> dict[str, Resource]:
    """Map active Resource rows into the scheduler's Resource dictionary."""

    rows = session.scalars(
        select(ResourceRow)
        .where(ResourceRow.active.is_(True))
        .order_by(ResourceRow.resource_code)
    ).all()
    return {
        row.resource_code: Resource(
            resource_code=row.resource_code,
            capacity=row.capacity,
        )
        for row in rows
    }


def _parse_hhmm(value: str) -> time:
    hour_text, minute_text = value.split(":", maxsplit=1)
    return time(int(hour_text), int(minute_text))


def load_work_calendar(session: Session, calendar_id: str) -> WorkCalendar:
    """Map one persisted recurring WorkCalendar into the core calendar."""

    row = session.get(WorkCalendarRow, calendar_id)
    if row is None:
        raise ValueError(f"unknown calendar_id: {calendar_id}")

    return WorkCalendar(
        timezone=row.timezone,
        work_start=_parse_hhmm(row.weekday_start),
        work_end=_parse_hhmm(row.weekday_end),
        active_weekdays=frozenset(row.active_weekdays),
    )
