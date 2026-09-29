"""Pure presentation helpers for the manager replan console."""

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from math import inf
from typing import Any

_RISK_RANK = {"URGENT": 0, "WARNING": 1, "NORMAL": 2}


@dataclass(frozen=True, slots=True)
class ReplanStatusSummary:
    """Current Forecast state relevant to the replan decision."""

    readiness: str
    risk_level: str
    lot_id: str | None
    gate_type: str | None
    slack_minutes: float | None


def summarize_replan_status(
    *,
    readiness: object,
    gate_rows: Sequence[Mapping[str, Any]],
) -> ReplanStatusSummary:
    """Pick the most severe Gate without inventing a new risk rule."""

    readiness_text = str(readiness)
    if readiness_text != "READY":
        return ReplanStatusSummary(
            readiness=readiness_text,
            risk_level="UNKNOWN",
            lot_id=None,
            gate_type=None,
            slack_minutes=None,
        )

    rows = [row for row in gate_rows if row.get("risk_level") in _RISK_RANK]
    if not rows:
        return ReplanStatusSummary(
            readiness=readiness_text,
            risk_level="UNKNOWN",
            lot_id=None,
            gate_type=None,
            slack_minutes=None,
        )

    def sort_key(row: Mapping[str, Any]) -> tuple[int, float, str]:
        slack = row.get("slack_minutes")
        numeric_slack = float(slack) if isinstance(slack, (int, float)) else inf
        return (
            _RISK_RANK[str(row["risk_level"])],
            numeric_slack,
            str(row.get("gate_id", "")),
        )

    selected = min(rows, key=sort_key)
    slack = selected.get("slack_minutes")
    return ReplanStatusSummary(
        readiness=readiness_text,
        risk_level=str(selected["risk_level"]),
        lot_id=str(selected.get("lot_id")) if selected.get("lot_id") is not None else None,
        gate_type=(
            str(selected.get("gate_type"))
            if selected.get("gate_type") is not None
            else None
        ),
        slack_minutes=float(slack) if isinstance(slack, (int, float)) else None,
    )


def build_priority_change_rows(
    *,
    current_tasks: Sequence[Mapping[str, Any]],
    candidate_tasks: Sequence[Mapping[str, Any]],
    lot_code_by_id: Mapping[str, str],
) -> tuple[dict[str, Any], ...]:
    """Compare candidate LOT x process priority ranks with the approved plan."""

    current_by_key = {
        (str(row.get("lot_id")), str(row.get("routing_step_id"))): row
        for row in current_tasks
        if row.get("lot_id") is not None and row.get("routing_step_id") is not None
    }

    changes: list[dict[str, Any]] = []
    for candidate in candidate_tasks:
        lot_id = candidate.get("lot_id")
        routing_step_id = candidate.get("routing_step_id")
        if lot_id is None or routing_step_id is None:
            continue

        key = (str(lot_id), str(routing_step_id))
        current = current_by_key.get(key)
        if current is None:
            continue

        current_rank = current.get("priority_rank")
        candidate_rank = candidate.get("priority_rank")
        if not isinstance(current_rank, int) or not isinstance(candidate_rank, int):
            continue
        if current_rank == candidate_rank:
            continue

        changes.append(
            {
                "lot_id": key[0],
                "lot_code": lot_code_by_id.get(key[0], key[0]),
                "routing_step_id": key[1],
                "process_code": current.get("process_code", key[1]),
                "current_rank": current_rank,
                "candidate_rank": candidate_rank,
                "movement": "앞당김" if candidate_rank < current_rank else "뒤로",
            }
        )

    changes.sort(
        key=lambda row: (
            int(row["candidate_rank"]),
            int(row["current_rank"]),
            str(row["lot_id"]),
            str(row["routing_step_id"]),
        )
    )
    return tuple(changes)
