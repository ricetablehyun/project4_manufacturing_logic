from datetime import datetime
from zoneinfo import ZoneInfo

from production_control.ui.operator_model import default_event_time

SEOUL = ZoneInfo("Asia/Seoul")


def dt(hour: int, minute: int = 0) -> datetime:
    return datetime(2026, 10, 5, hour, minute, tzinfo=SEOUL)


def test_default_event_time_prefers_current_time_over_old_eligible_time() -> None:
    operation = {
        "eligible_at": dt(9).isoformat(),
        "last_event_at": None,
    }

    assert default_event_time(operation, now=dt(10, 5)) == dt(10, 5)


def test_default_event_time_never_predates_future_eligible_time() -> None:
    operation = {
        "eligible_at": dt(11).isoformat(),
        "last_event_at": None,
    }

    assert default_event_time(operation, now=dt(10, 5)) == dt(11)
