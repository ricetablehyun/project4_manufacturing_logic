"""Pure display-model construction for the Streamlit Overview page."""

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime
from typing import Any

_RISK_RANK = {"URGENT": 0, "WARNING": 1, "NORMAL": 2}


@dataclass(frozen=True)
class OverviewView:
    plan_id: str
    plan_version: int
    readiness: str
    as_of: str
    urgent_lot_count: int
    warning_lot_count: int
    waiting_operation_count: int
    missing_gate_ids: tuple[str, ...]
    lot_rows: tuple[dict[str, Any], ...]
    gate_rows: tuple[dict[str, Any], ...]
    process_rows: tuple[dict[str, Any], ...]


def _format_datetime(value: object) -> str:
    if value in (None, ""):
        return "—"
    if isinstance(value, datetime):
        parsed = value
    elif isinstance(value, str):
        try:
            parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError:
            return value
    else:
        return str(value)
    return parsed.isoformat(timespec="minutes")


def _datetime_sort_value(value: object) -> str:
    if value in (None, ""):
        return "9999"
    return str(value)


def _risk_rank(value: object) -> int:
    return _RISK_RANK.get(str(value), 99)


def _mapping_by_id(
    rows: Sequence[Mapping[str, Any]],
    *,
    key: str,
) -> dict[str, Mapping[str, Any]]:
    return {str(row[key]): row for row in rows if row.get(key) is not None}


def build_overview_view(
    *,
    forecast: Mapping[str, Any],
    lots: Sequence[Mapping[str, Any]],
    gates: Sequence[Mapping[str, Any]],
) -> OverviewView:
    """Join API responses into deterministic, display-only dashboard rows."""

    forecast_lots = [row for row in forecast.get("lots", []) if isinstance(row, Mapping)]
    forecast_gates = [row for row in forecast.get("gates", []) if isinstance(row, Mapping)]
    forecast_processes = [
        row for row in forecast.get("processes", []) if isinstance(row, Mapping)
    ]

    forecast_lots_by_id = _mapping_by_id(forecast_lots, key="lot_id")
    admin_lots_by_id = _mapping_by_id(lots, key="lot_id")
    lot_ids = set(admin_lots_by_id) | set(forecast_lots_by_id)

    lot_rows: list[dict[str, Any]] = []
    for lot_id in lot_ids:
        admin = admin_lots_by_id.get(lot_id, {})
        current = forecast_lots_by_id.get(lot_id, {})
        lot_rows.append(
            {
                "lot_id": lot_id,
                "lot_code": admin.get("lot_code", lot_id),
                "status": admin.get("status", "UNKNOWN"),
                "quantity": admin.get("quantity"),
                "due_at": _format_datetime(admin.get("due_at")),
                "forecast_end": _format_datetime(current.get("forecast_end")),
                "risk_level": current.get("risk_level", "—"),
            }
        )
    lot_rows.sort(
        key=lambda row: (
            _risk_rank(row["risk_level"]),
            _datetime_sort_value(row["due_at"]),
            row["lot_id"],
        )
    )

    forecast_gates_by_id = _mapping_by_id(forecast_gates, key="gate_id")
    admin_gates_by_id = _mapping_by_id(gates, key="gate_id")
    gate_ids = set(admin_gates_by_id) | set(forecast_gates_by_id)

    gate_rows: list[dict[str, Any]] = []
    for gate_id in gate_ids:
        admin = admin_gates_by_id.get(gate_id, {})
        current = forecast_gates_by_id.get(gate_id, {})
        gate_rows.append(
            {
                "gate_id": gate_id,
                "lot_id": admin.get("lot_id", current.get("lot_id", "—")),
                "gate_type": admin.get("gate_type", current.get("gate_type", "—")),
                "status": admin.get("status", "UNKNOWN"),
                "planned_at": _format_datetime(
                    current.get("planned_at", admin.get("planned_at"))
                ),
                "forecast_at": _format_datetime(current.get("forecast_at")),
                "slack_minutes": current.get("slack_minutes"),
                "risk_level": current.get("risk_level", "—"),
                "completed_at": _format_datetime(admin.get("completed_at")),
            }
        )
    gate_rows.sort(
        key=lambda row: (
            _risk_rank(row["risk_level"]),
            _datetime_sort_value(row["planned_at"]),
            row["gate_id"],
        )
    )

    process_rows = [
        {
            "lot_id": row.get("lot_id", "—"),
            "process_code": row.get("process_code", "—"),
            "forecast_start": _format_datetime(row.get("forecast_start")),
            "forecast_end": _format_datetime(row.get("forecast_end")),
            "scheduled_operation_count": row.get("scheduled_operation_count"),
        }
        for row in forecast_processes
    ]
    process_rows.sort(
        key=lambda row: (
            row["lot_id"],
            _datetime_sort_value(row["forecast_start"]),
            row["process_code"],
        )
    )

    urgent_count = sum(row.get("risk_level") == "URGENT" for row in forecast_lots)
    warning_count = sum(row.get("risk_level") == "WARNING" for row in forecast_lots)
    waiting_ids = forecast.get("waiting_operation_ids", [])
    missing_gate_ids = tuple(str(value) for value in forecast.get("missing_gate_ids", []))

    return OverviewView(
        plan_id=str(forecast.get("plan_id", "—")),
        plan_version=int(forecast.get("plan_version", 0)),
        readiness=str(forecast.get("readiness", "UNKNOWN")),
        as_of=_format_datetime(forecast.get("as_of")),
        urgent_lot_count=urgent_count,
        warning_lot_count=warning_count,
        waiting_operation_count=len(waiting_ids) if isinstance(waiting_ids, list) else 0,
        missing_gate_ids=missing_gate_ids,
        lot_rows=tuple(lot_rows),
        gate_rows=tuple(gate_rows),
        process_rows=tuple(process_rows),
    )
