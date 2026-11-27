"""Render the report and slide figures from recorded data.

    python -m production_control.sim.figures --experiment experiments/main30 --out docs/figures

Every figure is drawn from a file or a deterministic computation:

- ``gate_delay.png``, ``overtime_tradeoff.png``, ``run_distribution.png`` come
  from the experiment's ``summary.csv`` / ``runs.csv``.
- ``gantt_replan.png`` is the demo start state (2026-10-22 13:00, FCFS baseline):
  the current Forecast under the kept plan versus the EDD replanning candidate,
  both computed by the API from the same database.

The charts are the same definitions the dashboard shows (``ui/charts.py``).
PNG export needs ``vl-convert-python`` (``pip install -e ".[figures]"``).
"""

from __future__ import annotations

import argparse
import csv
import json
import tempfile
from collections.abc import Sequence
from datetime import datetime
from pathlib import Path

from production_control.sim.experiment import BASELINE_LOT_ORDER, DEMO_START_ISO
from production_control.ui import charts
from production_control.ui.gantt_model import (
    CANDIDATE_LAYER,
    FORECAST_LAYER,
    forecast_bars,
    gate_markers,
    plan_bars,
    plant_time,
    records,
    step_process_map,
)

KOREAN_FONT_DIRS = ("/usr/share/fonts/truetype/wqy", "/usr/share/fonts/truetype/nanum")
FONT = "WenQuanYi Zen Hei, NanumGothic, Malgun Gothic, AppleGothic, sans-serif"


def _read_csv(path: Path) -> list[dict[str, str]]:
    with path.open(encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle))


def demo_replan_gantt_data(candidate_id: str = "EDD") -> dict[str, object]:
    """Forecast vs one candidate at the demo start, from a fresh demo world."""

    from production_control.sim.harness import build_harness
    from production_control.sim.truth import TruthModel
    from production_control.sim.worlds import build_demo_world

    start = datetime.fromisoformat(DEMO_START_ISO)
    with tempfile.TemporaryDirectory(prefix="pc-fig-") as tmp:
        database = build_demo_world(Path(tmp) / "world.db", baseline_lot_order=BASELINE_LOT_ORDER)
        terminal = build_harness(
            database, truth=TruthModel(), start_time=start, run_tag="figure"
        ).terminal
        lots = {row["lot_id"]: row["lot_code"] for row in terminal.lots()}
        operations = terminal.unit_operations()
        forecast = terminal.forecast(start)
        snapshot = terminal.replan_candidates(start)
        gates = [g for g in terminal.gates() if g["gate_type"] == "SHIPPING_INSPECTION"]
    candidate = next(c for c in snapshot["candidates"] if c["candidate_id"] == candidate_id)
    steps = step_process_map(operations)
    bars = forecast_bars(forecast["processes"], lot_labels=lots) + plan_bars(
        candidate["tasks"], lot_labels=lots, layer=CANDIDATE_LAYER, step_process=steps
    )
    forecast_risk = {lot["lot_id"]: lot["risk_level"] for lot in forecast["lots"]}
    return {
        "bars": records(bars),
        "markers": records(gate_markers(gates, lot_labels=lots)),
        "now": plant_time(start),
        "candidate_id": candidate_id,
        "candidate_kpi": candidate["kpi"],
        "forecast_risk": forecast_risk,
    }


def _themed(chart):
    return chart.configure(font=FONT, background="white").configure_view(stroke=None)


def render(experiment: Path, out: Path, *, scale: float = 2.0) -> list[Path]:
    import vl_convert as vlc

    for directory in KOREAN_FONT_DIRS:
        if Path(directory).is_dir():
            vlc.register_font_directory(directory)

    out.mkdir(parents=True, exist_ok=True)
    summary = charts.summary_records(_read_csv(experiment / "summary.csv"))
    runs = _read_csv(experiment / "runs.csv")
    gantt = demo_replan_gantt_data()
    (out / "gantt_replan.json").write_text(
        json.dumps(gantt, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    figures = {
        "gate_delay.png": charts.gate_delay_chart(summary),
        "overtime_tradeoff.png": charts.overtime_tradeoff_chart(summary),
        "run_distribution.png": charts.run_distribution_chart(runs),
        "gantt_replan.png": charts.gantt_chart(
            gantt["bars"],
            markers=gantt["markers"],
            now=gantt["now"],
            layers=(FORECAST_LAYER, CANDIDATE_LAYER),
        ).properties(width=900),
    }
    written = []
    for name, chart in figures.items():
        png = vlc.vegalite_to_png(_themed(chart).to_json(), scale=scale)
        path = out / name
        path.write_bytes(png)
        written.append(path)
    return written


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--experiment", type=Path, default=Path("experiments/main30"))
    parser.add_argument("--out", type=Path, default=Path("docs/figures"))
    args = parser.parse_args(argv)
    for path in render(args.experiment, args.out):
        print(path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
