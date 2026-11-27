"""Pure Gantt rows for the administrator UI.

A bar is one LOT x process window on one layer: the approved plan, the current
Forecast, or a replanning candidate. Times are converted to naive Asia/Seoul
wall-clock strings so the chart shows plant time in any browser time zone.
"""

from collections.abc import Iterable, Mapping
from dataclasses import asdict, dataclass
from datetime import datetime
from zoneinfo import ZoneInfo

from production_control.ui.display_labels import gate_type_label, process_label

SEOUL = ZoneInfo("Asia/Seoul")

PLAN_LAYER = "승인 계획"
FORECAST_LAYER = "현재 Forecast"
CANDIDATE_LAYER = "재계획안"

PROCESS_ORDER = (
    "TAPING",
    "EXTERNAL_FEED_BONDING",
    "GENERAL_ASSEMBLY",
    "TUNING",
    "FINISH_ASSEMBLY",
    "FINAL_TEST",
)


@dataclass(frozen=True)
class GanttBar:
    lot_id: str
    lot_label: str
    process_code: str
    process_label: str
    layer: str
    start: str
    end: str


@dataclass(frozen=True)
class GanttMarker:
    lot_id: str
    lot_label: str
    label: str
    at: str


def _parse(value: object) -> datetime | None:
    if isinstance(value, datetime):
        parsed = value
    elif isinstance(value, str) and value:
        try:
            parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError:
            return None
    else:
        return None
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        return None
    return parsed


def plant_time(value: object) -> str | None:
    """Naive Asia/Seoul ISO string, or None when the value is not an aware time."""

    parsed = _parse(value)
    if parsed is None:
        return None
    return parsed.astimezone(SEOUL).replace(tzinfo=None).isoformat(timespec="minutes")


def _bar(
    *,
    lot_id: str,
    process_code: str,
    layer: str,
    start: object,
    end: object,
    lot_labels: Mapping[str, str],
) -> GanttBar | None:
    start_text, end_text = plant_time(start), plant_time(end)
    if start_text is None or end_text is None or end_text <= start_text:
        return None
    return GanttBar(
        lot_id=lot_id,
        lot_label=lot_labels.get(lot_id, lot_id),
        process_code=process_code,
        process_label=process_label(process_code),
        layer=layer,
        start=start_text,
        end=end_text,
    )


def plan_bars(
    tasks: Iterable[Mapping[str, object]],
    *,
    lot_labels: Mapping[str, str],
    layer: str = PLAN_LAYER,
    step_process: Mapping[tuple[str, str], str] | None = None,
) -> list[GanttBar]:
    """Bars from plan or candidate tasks (``target_start`` / ``target_end``).

    Candidate tasks carry no process code, so ``step_process`` maps
    ``(lot_id, routing_step_id)`` to it; tasks it cannot place are left out.
    """

    bars: list[GanttBar] = []
    for task in tasks:
        lot_id = str(task.get("lot_id", ""))
        process_code = task.get("process_code")
        if process_code is None and step_process is not None:
            process_code = step_process.get((lot_id, str(task.get("routing_step_id"))))
        if not lot_id or process_code is None:
            continue
        bar = _bar(
            lot_id=lot_id,
            process_code=str(process_code),
            layer=layer,
            start=task.get("target_start"),
            end=task.get("target_end"),
            lot_labels=lot_labels,
        )
        if bar is not None:
            bars.append(bar)
    return bars


def forecast_bars(
    processes: Iterable[Mapping[str, object]],
    *,
    lot_labels: Mapping[str, str],
) -> list[GanttBar]:
    """Bars for the remaining work of each LOT x process in the live Forecast."""

    bars: list[GanttBar] = []
    for row in processes:
        bar = _bar(
            lot_id=str(row.get("lot_id", "")),
            process_code=str(row.get("process_code", "")),
            layer=FORECAST_LAYER,
            start=row.get("forecast_start"),
            end=row.get("forecast_end"),
            lot_labels=lot_labels,
        )
        if bar is not None:
            bars.append(bar)
    return bars


def gate_markers(
    gates: Iterable[Mapping[str, object]],
    *,
    lot_labels: Mapping[str, str],
) -> list[GanttMarker]:
    """Planned times of Gates that are not completed yet."""

    markers: list[GanttMarker] = []
    for gate in gates:
        if gate.get("completed_at"):
            continue
        at = plant_time(gate.get("planned_at"))
        lot_id = str(gate.get("lot_id", ""))
        if at is None or not lot_id:
            continue
        markers.append(
            GanttMarker(
                lot_id=lot_id,
                lot_label=lot_labels.get(lot_id, lot_id),
                label=f"{gate_type_label(gate.get('gate_type'))} 예정",
                at=at,
            )
        )
    return markers


def step_process_map(
    tasks: Iterable[Mapping[str, object]],
) -> dict[tuple[str, str], str]:
    return {
        (str(task.get("lot_id")), str(task.get("routing_step_id"))): str(task["process_code"])
        for task in tasks
        if task.get("process_code") is not None
    }


def records(items: Iterable[GanttBar | GanttMarker]) -> list[dict[str, str]]:
    return [asdict(item) for item in items]
