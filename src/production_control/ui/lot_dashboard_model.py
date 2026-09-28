"""Pure LOT-first presentation helpers for the Streamlit production dashboard."""

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any

PROCESS_ORDER = (
    "TAPING",
    "GENERAL_ASSEMBLY",
    "TUNING",
    "FINISH_ASSEMBLY",
    "FINAL_TEST",
)


@dataclass(frozen=True, slots=True)
class ProcessProgress:
    process_code: str
    completed: int
    total: int
    running: int
    hold: int
    waiting: int

    @property
    def fraction(self) -> float:
        if self.total <= 0:
            return 0.0
        return self.completed / self.total


@dataclass(frozen=True, slots=True)
class LotProgressSummary:
    lot_id: str
    processes: tuple[ProcessProgress, ...]
    current_process_code: str | None


def build_lot_progress(
    operations: Sequence[Mapping[str, Any]],
    *,
    lot_id: str,
) -> LotProgressSummary:
    """Aggregate UnitOperation execution states into compact per-process progress."""

    lot_operations = [row for row in operations if row.get("lot_id") == lot_id]
    by_process: dict[str, list[Mapping[str, Any]]] = {
        process_code: [] for process_code in PROCESS_ORDER
    }
    for row in lot_operations:
        process_code = str(row.get("process_code", ""))
        if process_code in by_process:
            by_process[process_code].append(row)

    progresses: list[ProcessProgress] = []
    current_process_code: str | None = None
    for process_code in PROCESS_ORDER:
        rows = by_process[process_code]
        total = len(rows)
        completed = sum(str(row.get("state")) == "COMPLETED" for row in rows)
        running = sum(str(row.get("state")) == "RUNNING" for row in rows)
        hold = sum(str(row.get("state")) == "HOLD" for row in rows)
        waiting = sum(str(row.get("state")) == "WAITING" for row in rows)
        progresses.append(
            ProcessProgress(
                process_code=process_code,
                completed=completed,
                total=total,
                running=running,
                hold=hold,
                waiting=waiting,
            )
        )
        if current_process_code is None and total > 0 and completed < total:
            current_process_code = process_code

    return LotProgressSummary(
        lot_id=lot_id,
        processes=tuple(progresses),
        current_process_code=current_process_code,
    )


def build_process_unit_rows(
    operations: Sequence[Mapping[str, Any]],
    *,
    lot_id: str,
) -> tuple[dict[str, Any], ...]:
    """Group one LOT's UnitOperations by process and execution state."""

    lot_operations = [row for row in operations if row.get("lot_id") == lot_id]
    rows: list[dict[str, Any]] = []

    for process_code in PROCESS_ORDER:
        process_operations = [
            row for row in lot_operations if str(row.get("process_code")) == process_code
        ]
        if not process_operations:
            continue

        units_by_state: dict[str, list[str]] = {
            "COMPLETED": [],
            "RUNNING": [],
            "HOLD": [],
            "WAITING": [],
        }
        for operation in process_operations:
            state = str(operation.get("state", "UNKNOWN"))
            if state not in units_by_state:
                continue
            unit_code = str(operation.get("unit_code") or operation.get("unit_id") or "—")
            units_by_state[state].append(unit_code)

        for unit_codes in units_by_state.values():
            unit_codes.sort()

        rows.append(
            {
                "process_code": process_code,
                "completed": len(units_by_state["COMPLETED"]),
                "total": len(process_operations),
                "completed_units": tuple(units_by_state["COMPLETED"]),
                "running_units": tuple(units_by_state["RUNNING"]),
                "hold_units": tuple(units_by_state["HOLD"]),
                "waiting_units": tuple(units_by_state["WAITING"]),
            }
        )

    return tuple(rows)


def build_unit_detail_rows(
    operations: Sequence[Mapping[str, Any]],
    *,
    lot_id: str,
) -> tuple[dict[str, Any], ...]:
    """Build one compact execution row per Unit using its earliest unfinished process."""

    lot_operations = [row for row in operations if row.get("lot_id") == lot_id]
    unit_ids = sorted({str(row.get("unit_id")) for row in lot_operations if row.get("unit_id")})
    result: list[dict[str, Any]] = []

    for unit_id in unit_ids:
        unit_rows = [row for row in lot_operations if str(row.get("unit_id")) == unit_id]
        unit_rows.sort(key=lambda row: int(row.get("seq_no", 10**9)))
        current = next(
            (
                row
                for row in unit_rows
                if str(row.get("state")) != "COMPLETED"
                or (
                    str(row.get("process_code")) == "FINAL_TEST"
                    and not row.get("result")
                )
            ),
            None,
        )
        if current is None:
            sample = unit_rows[-1] if unit_rows else {}
            result.append(
                {
                    "unit_code": sample.get("unit_code", unit_id),
                    "process_code": "—",
                    "state": "COMPLETED",
                    "attempt_no": sample.get("attempt_no", 1),
                    "active_minutes": sample.get("active_minutes", 0.0),
                }
            )
            continue

        result.append(
            {
                "unit_code": current.get("unit_code", unit_id),
                "process_code": current.get("process_code", "—"),
                "state": current.get("state", "UNKNOWN"),
                "attempt_no": current.get("attempt_no", 1),
                "active_minutes": current.get("active_minutes", 0.0),
            }
        )

    return tuple(result)


def minimum_gate_slack(
    gate_rows: Sequence[Mapping[str, Any]],
    *,
    lot_id: str,
) -> float | None:
    """Return the tightest numeric Gate slack for one LOT."""

    values: list[float] = []
    for row in gate_rows:
        if row.get("lot_id") != lot_id:
            continue
        value = row.get("slack_minutes")
        if isinstance(value, (int, float)):
            values.append(float(value))
    return min(values) if values else None
