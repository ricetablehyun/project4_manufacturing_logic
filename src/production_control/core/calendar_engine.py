"""Work-calendar calculations used by the finite-capacity scheduler."""

from collections.abc import Iterable
from dataclasses import dataclass, replace
from datetime import date, datetime, time, timedelta
from zoneinfo import ZoneInfo

# Durations are float minutes (Pace averages) while datetimes resolve to
# microseconds. A remainder below this tolerance is rounding noise, not work;
# without it a 1e-9 minute tail became a zero-length segment on the next day.
MINUTE_TOLERANCE = 1e-6


@dataclass(frozen=True, slots=True)
class WorkSegment:
    """One contiguous working-time segment."""

    start: datetime
    end: datetime

    def __post_init__(self) -> None:
        if self.start >= self.end:
            raise ValueError("work segment start must be earlier than end")


@dataclass(frozen=True, slots=True)
class WorkCalendar:
    """Recurring weekly work calendar.

    Datetimes passed to this class must be timezone-aware. V1 uses a common
    Monday-Friday calendar. ``overtime`` extends the closing time of specific
    working days (D078): each entry is ``(day, extended_end)`` and applies to
    the whole plant, because approved overtime keeps every station staffed.
    """

    timezone: str = "Asia/Seoul"
    work_start: time = time(9, 0)
    work_end: time = time(17, 0)
    active_weekdays: frozenset[int] = frozenset({0, 1, 2, 3, 4})
    overtime: tuple[tuple[date, time], ...] = ()

    def __post_init__(self) -> None:
        if self.work_start >= self.work_end:
            raise ValueError("work_start must be earlier than work_end")
        if not self.active_weekdays:
            raise ValueError("active_weekdays must not be empty")
        if any(day < 0 or day > 6 for day in self.active_weekdays):
            raise ValueError("active_weekdays must contain values from 0 to 6")
        days = [day for day, _ in self.overtime]
        if len(days) != len(set(days)):
            raise ValueError("overtime days must be unique")
        for day, extended_end in self.overtime:
            if day.weekday() not in self.active_weekdays:
                raise ValueError(f"overtime day is not a working day: {day}")
            if extended_end <= self.work_end:
                raise ValueError(f"overtime must end after work_end: {day} {extended_end}")

    @property
    def tz(self) -> ZoneInfo:
        return ZoneInfo(self.timezone)

    def _require_aware(self, value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("datetime must be timezone-aware")
        return value.astimezone(self.tz)

    def _day_start(self, value: datetime) -> datetime:
        return datetime.combine(value.date(), self.work_start, tzinfo=self.tz)

    def _day_end(self, value: datetime) -> datetime:
        for day, extended_end in self.overtime:
            if day == value.date():
                return datetime.combine(day, extended_end, tzinfo=self.tz)
        return datetime.combine(value.date(), self.work_end, tzinfo=self.tz)

    @property
    def overtime_days(self) -> frozenset[date]:
        return frozenset(day for day, _ in self.overtime)

    def with_overtime(self, days: Iterable[date], extended_end: time) -> "WorkCalendar":
        """Return this calendar with ``days`` (added to existing ones) closing later."""

        merged = dict(self.overtime)
        for day in days:
            merged.setdefault(day, extended_end)
        return replace(self, overtime=tuple(sorted(merged.items())))

    def closing_time(self, day: date) -> datetime:
        """Closing time of ``day`` including approved overtime."""

        return self._day_end(datetime.combine(day, time.min, tzinfo=self.tz))

    def regular_close(self, day: date) -> datetime:
        """Closing time of ``day`` without overtime."""

        return datetime.combine(day, self.work_end, tzinfo=self.tz)

    def is_working_time(self, value: datetime) -> bool:
        local = self._require_aware(value)
        if local.weekday() not in self.active_weekdays:
            return False
        return self._day_start(local) <= local < self._day_end(local)

    def next_work_start(self, value: datetime) -> datetime:
        """Return value itself if already working, otherwise the next opening."""

        local = self._require_aware(value)
        for day_offset in range(8):
            day = local + timedelta(days=day_offset)
            if day.weekday() not in self.active_weekdays:
                continue

            opening = self._day_start(day)
            closing = self._day_end(day)

            if day_offset == 0:
                if local < opening:
                    return opening
                if opening <= local < closing:
                    return local
                continue

            return opening

        raise RuntimeError("could not find the next working day")

    def add_working_minutes(self, start: datetime, minutes: float) -> datetime:
        """Advance through only recurring working intervals."""

        if minutes < 0:
            raise ValueError("minutes must be 0 or greater")

        current = self.next_work_start(start)
        remaining = float(minutes)

        if remaining == 0:
            return current

        while remaining > 0:
            closing = self._day_end(current)
            available = (closing - current).total_seconds() / 60

            if remaining <= available + MINUTE_TOLERANCE:
                return current + timedelta(minutes=min(remaining, available))

            remaining -= available
            current = self.next_work_start(closing)

        return current

    def working_segments(self, start: datetime, minutes: float) -> tuple[WorkSegment, ...]:
        """Split work across calendar boundaries without counting closed time."""

        if minutes <= 0:
            raise ValueError("minutes must be greater than 0")

        current = self.next_work_start(start)
        remaining = float(minutes)
        segments: list[WorkSegment] = []

        while not segments or remaining > MINUTE_TOLERANCE:
            closing = self._day_end(current)
            available = (closing - current).total_seconds() / 60
            if remaining <= available + MINUTE_TOLERANCE:
                segment_minutes = min(remaining, available)
            else:
                segment_minutes = available
            segment_end = current + timedelta(minutes=segment_minutes)
            segments.append(WorkSegment(start=current, end=segment_end))
            remaining -= segment_minutes

            if remaining > MINUTE_TOLERANCE:
                current = self.next_work_start(closing)

        return tuple(segments)

    def working_minutes_between(self, start: datetime, end: datetime) -> float:
        """Count recurring working minutes in [start, end)."""

        local_start = self._require_aware(start)
        local_end = self._require_aware(end)
        if local_end < local_start:
            raise ValueError("end must not be earlier than start")

        total = 0.0
        cursor = local_start
        while cursor.date() <= local_end.date():
            if cursor.weekday() in self.active_weekdays:
                day_start = self._day_start(cursor)
                day_end = self._day_end(cursor)
                overlap_start = max(local_start, day_start)
                overlap_end = min(local_end, day_end)
                if overlap_start < overlap_end:
                    total += (overlap_end - overlap_start).total_seconds() / 60

            cursor = datetime.combine(
                cursor.date() + timedelta(days=1),
                time.min,
                tzinfo=self.tz,
            )

        return total

    def working_minutes_until(
        self,
        reference: datetime,
        deadline: datetime,
    ) -> float:
        """Return signed WorkCalendar minutes from reference to deadline."""

        local_reference = self._require_aware(reference)
        local_deadline = self._require_aware(deadline)

        if local_deadline >= local_reference:
            return self.working_minutes_between(local_reference, local_deadline)

        return -self.working_minutes_between(local_deadline, local_reference)
