"""SQLite-safe timezone-aware datetime storage."""

from datetime import datetime

from sqlalchemy import String
from sqlalchemy.engine import Dialect
from sqlalchemy.types import TypeDecorator


class OffsetDateTime(TypeDecorator):
    """Store aware datetimes as ISO-8601 text, preserving their UTC offset."""

    impl = String
    cache_ok = True

    def process_bind_param(
        self,
        value: datetime | None,
        dialect: Dialect,
    ) -> str | None:
        del dialect
        if value is None:
            return None
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("OffsetDateTime requires a timezone-aware datetime")
        return value.isoformat()

    def process_result_value(
        self,
        value: str | None,
        dialect: Dialect,
    ) -> datetime | None:
        del dialect
        if value is None:
            return None
        parsed = datetime.fromisoformat(value)
        if parsed.tzinfo is None or parsed.utcoffset() is None:
            raise ValueError("stored OffsetDateTime value is missing an offset")
        return parsed
