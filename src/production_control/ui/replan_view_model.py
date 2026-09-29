"""Pure presentation helpers for the manager replan console."""

from collections import Counter
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime
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


def _numeric_kpi_value(kpi: Mapping[str, Any], key: str) -> float:
    value = kpi.get(key)
    if isinstance(value, (int, float)):
        return float(value)
    return inf


def _candidate_kpi_key(candidate: Mapping[str, Any]) -> tuple[float, float, float, float]:
    """Return the already-confirmed D029 lexicographic KPI key."""

    kpi = candidate.get("kpi")
    if not isinstance(kpi, Mapping):
        return (inf, inf, inf, inf)
    return (
        _numeric_kpi_value(kpi, "late_lot_count"),
        _numeric_kpi_value(kpi, "total_tardiness_minutes"),
        _numeric_kpi_value(kpi, "overtime_minutes"),
        _numeric_kpi_value(kpi, "change_count"),
    )


def rank_replan_candidates(
    candidates: Sequence[Mapping[str, Any]],
) -> tuple[dict[str, Any], ...]:
    """Order replan options best-first without inventing a weighted score.

    D073 policy-compliant candidates are ranked first by D029. Exact KPI ties
    share the same rank. Policy-violating candidates remain visible at the end
    but do not receive an approval rank.
    """

    valid = [
        candidate
        for candidate in candidates
        if candidate.get("candidate_id") is not None
    ]
    compliant = [
        candidate for candidate in valid if candidate.get("policy_compliant") is True
    ]
    violating = [
        candidate for candidate in valid if candidate.get("policy_compliant") is not True
    ]

    ordered_compliant = sorted(compliant, key=_candidate_kpi_key)
    key_counts = Counter(_candidate_kpi_key(candidate) for candidate in ordered_compliant)

    ranked: list[dict[str, Any]] = []
    previous_key: tuple[float, float, float, float] | None = None
    current_rank = 0
    for position, candidate in enumerate(ordered_compliant, start=1):
        key = _candidate_kpi_key(candidate)
        if key != previous_key:
            current_rank = position
        ranked.append(
            {
                "candidate_id": str(candidate["candidate_id"]),
                "rank": current_rank,
                "tied": key_counts[key] > 1,
                "policy_compliant": True,
            }
        )
        previous_key = key

    for candidate in violating:
        ranked.append(
            {
                "candidate_id": str(candidate["candidate_id"]),
                "rank": None,
                "tied": False,
                "policy_compliant": False,
            }
        )

    return tuple(ranked)


def _parse_datetime(value: object) -> datetime | None:
    if isinstance(value, datetime):
        return value
    if not isinstance(value, str) or not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None


def _shift_minutes(current: object, candidate: object) -> float | None:
    current_dt = _parse_datetime(current)
    candidate_dt = _parse_datetime(candidate)
    if current_dt is None or candidate_dt is None:
        return None
    if (
        current_dt.tzinfo is None
        or current_dt.utcoffset() is None
        or candidate_dt.tzinfo is None
        or candidate_dt.utcoffset() is None
    ):
        return None
    return (candidate_dt - current_dt).total_seconds() / 60


def build_plan_change_rows(
    *,
    current_tasks: Sequence[Mapping[str, Any]],
    candidate_tasks: Sequence[Mapping[str, Any]],
    lot_code_by_id: Mapping[str, str],
) -> tuple[dict[str, Any], ...]:
    """Show every LOT x process plan-window or priority change."""

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

        current_start = current.get("target_start")
        candidate_start = candidate.get("target_start")
        current_end = current.get("target_end")
        candidate_end = candidate.get("target_end")
        current_rank = current.get("priority_rank")
        candidate_rank = candidate.get("priority_rank")

        if (
            current_start == candidate_start
            and current_end == candidate_end
            and current_rank == candidate_rank
        ):
            continue

        priority_movement = "유지"
        if isinstance(current_rank, int) and isinstance(candidate_rank, int):
            if candidate_rank < current_rank:
                priority_movement = "앞당김"
            elif candidate_rank > current_rank:
                priority_movement = "뒤로"

        changes.append(
            {
                "lot_id": key[0],
                "lot_code": lot_code_by_id.get(key[0], key[0]),
                "routing_step_id": key[1],
                "process_code": current.get("process_code", key[1]),
                "current_start": current_start,
                "candidate_start": candidate_start,
                "current_end": current_end,
                "candidate_end": candidate_end,
                "start_shift_minutes": _shift_minutes(current_start, candidate_start),
                "end_shift_minutes": _shift_minutes(current_end, candidate_end),
                "current_rank": current_rank,
                "candidate_rank": candidate_rank,
                "priority_movement": priority_movement,
            }
        )

    changes.sort(
        key=lambda row: (
            int(row["candidate_rank"])
            if isinstance(row.get("candidate_rank"), int)
            else 10**9,
            str(row["lot_id"]),
            str(row["routing_step_id"]),
        )
    )
    return tuple(changes)


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
