"""Pure presentation helpers for operator event input."""

from collections.abc import Mapping, Sequence
from datetime import UTC, datetime, timedelta
from typing import Any


def parse_api_datetime(value: object) -> datetime | None:
    if not isinstance(value, str) or not value:
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        return None
    return parsed


def current_operation_for_unit(
    operations: Sequence[Mapping[str, Any]],
    *,
    lot_id: str,
    unit_id: str,
) -> Mapping[str, Any] | None:
    candidates = [
        row
        for row in operations
        if row.get("lot_id") == lot_id
        and row.get("unit_id") == unit_id
        and row.get("state") != "COMPLETED"
    ]
    if not candidates:
        return None
    return min(candidates, key=lambda row: int(row.get("seq_no", 10**9)))


def allowed_event_types(operation: Mapping[str, Any]) -> tuple[str, ...]:
    state = str(operation.get("state", ""))
    process_code = str(operation.get("process_code", ""))
    if state == "WAITING":
        return ("START",)
    if state == "RUNNING":
        if process_code == "FINAL_TEST":
            return ("HOLD", "PASS", "FAIL")
        return ("HOLD", "COMPLETE")
    if state == "HOLD":
        return ("RESUME",)
    if state == "COMPLETED" and process_code == "FINAL_TEST" and not operation.get("result"):
        return ("PASS", "FAIL")
    return ()


def reason_required(*, event_type: str, process_code: str) -> bool:
    return event_type == "HOLD" or (
        event_type == "FAIL" and process_code == "FINAL_TEST"
    )


def default_event_time(operation: Mapping[str, Any]) -> datetime:
    last_event_at = parse_api_datetime(operation.get("last_event_at"))
    if last_event_at is not None:
        return last_event_at + timedelta(minutes=10)
    eligible_at = parse_api_datetime(operation.get("eligible_at"))
    if eligible_at is not None:
        return eligible_at
    return datetime.now(UTC)


def latest_execution_reference(
    operations: Sequence[Mapping[str, Any]],
    *,
    now: datetime,
) -> datetime:
    """Choose a reference time that never predates persisted execution facts."""

    if now.tzinfo is None or now.utcoffset() is None:
        raise ValueError("now must be timezone-aware")
    event_times = [
        parsed
        for row in operations
        if (parsed := parse_api_datetime(row.get("last_event_at"))) is not None
    ]
    return max((now, *event_times))
