"""Work-calendar calculations used by the finite-capacity scheduler."""

from dataclasses import dataclass
from datetime import datetime, time, timedelta
from zoneinfo import ZoneInfo


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
    Monday-Friday calendar and may layer resource exceptions on top elsewhere.
    """

    timezone: str = "Asia/Seoul"
    work_start: time = time(9, 0)
    work_end: time = time(17, 0)
    active_weekdays: frozenset[int] = frozenset({0, 1, 2, 3, 4})

    def __post_init__(self) -> None:
        if self.work_start >= self.work_end:
            raise ValueError("work_start must be earlier than work_end")
        if not self.active_weekdays:
            raise ValueError("active_weekdays must not be empty")
        if any(day < 0 or day > 6 for day in self.active_weekdays):
            raise ValueError("active_weekdays must contain values from 0 to 6")

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
        return datetime.combine(value.date(), self.work_end, tzinfo=self.tz)

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

            if remaining <= available:
                return current + timedelta(minutes=remaining)

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

        while remaining > 0:
            closing = self._day_end(current)
            available = (closing - current).total_seconds() / 60
            segment_minutes = min(remaining, available)
            segment_end = current + timedelta(minutes=segment_minutes)
            segments.append(WorkSegment(start=current, end=segment_end))
            remaining -= segment_minutes

            if remaining > 0:
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
