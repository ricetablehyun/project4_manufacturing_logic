"""Repeated closed-loop experiments: policies x conditions x overtime x seeds.

One command reproduces every number::

    python -m production_control.sim.experiment --reps 10 --out experiments/pilot

Design
------
- Start state: the midterm presentation situation (3 LOTs x 30 Units,
  2026-10-22 13:00) with a first-come-first-served baseline plan, under which
  LOT-103 (earlier Gate than LOT-102) is served last.
- Policies: KEEP (never replan) and the four rules the manager approves when
  the system reports URGENT. With overtime on, the manager may take the rule's
  "+OT" candidate (D078). KEEP with overtime is the same run as KEEP and is
  not repeated.
- Conditions change only the hidden truth of the virtual plant; the system
  sees WorkEvents and worker estimates, never the truth.
- Common random numbers: replication ``r`` uses seed ``r`` for every policy,
  and each draw is keyed by (operation, attempt), so a Unit's true time and
  test result are identical across policies.

Metrics (per run, all LOTs)
---------------------------
- Shipping-inspection entry delay: wall-clock minutes from the Gate's planned
  start (InspectionGate.planned_at) to the LOT's last FINAL_TEST pass, 0 if on
  time. This is the system's own tardiness definition.
- Final due tardiness: the LOT ships after shipping inspection, assumed to
  take ``INSPECTION_LEAD_WORKING_MINUTES`` of regular working time after the
  last FINAL_TEST pass; tardiness against Lot.due_at, 0 if on time. The lead
  time is an assumption stated with every result.
- On-time delivery rate: share of LOTs with zero final due tardiness.
- Mean completion: mean over LOTs of regular working hours from the run start
  to the LOT's last FINAL_TEST pass.
- Overtime (extra operating time): per approved overtime day, minutes from
  the regular close (17:00) to the last work end inside the window. Idle gaps
  in that span count; it is not the sum of busy work minutes.

Scope: the virtual terminal talks HTTP to the FastAPI app through an
in-process TestClient (same routing, validation, serialisation). A separate
test runs the same closed loop over a real localhost socket (uvicorn +
httpx). Neither involves the Pico 2 WH hardware, which is not integrated.
"""

from __future__ import annotations

import argparse
import csv
import json
import math
import os
import platform
import subprocess
import sys
import tempfile
import time as wall_time
from collections.abc import Iterable, Sequence
from concurrent.futures import ProcessPoolExecutor, as_completed
from dataclasses import asdict, dataclass, replace
from datetime import datetime, time
from pathlib import Path
from statistics import NormalDist, mean, stdev

from production_control.core.calendar_engine import WorkCalendar
from production_control.sim.harness import DEFAULT_FORECAST_CONFIG, build_harness
from production_control.sim.manager import ApprovalPolicy
from production_control.sim.runner import RunResult
from production_control.sim.truth import TruthModel

DEMO_START_ISO = "2026-10-22T13:00:00+09:00"
BASELINE_LOT_ORDER = ("LOT-101", "LOT-102", "LOT-103")
INSPECTION_LEAD_WORKING_MINUTES = 3 * 8 * 60  # 3 working days (assumption)
OVERTIME_END = time(19, 0)

CONDITIONS: dict[str, dict[str, float]] = {
    # random spread around the standard times, unbiased on average
    "NORMAL": {"duration_sigma": 0.15, "estimate_sigma": 0.2},
    # true work times 20% longer than the standards on average
    "SLOW": {"duration_sigma": 0.15, "estimate_sigma": 0.2, "duration_multiplier": 1.2},
    # mid-work stoppages (3% of attempts need 240 more working minutes; a delay
    # model, not HOLD/RESUME events) and 8% FINAL_TEST failures with rework
    "STOPPAGE_REWORK": {
        "duration_sigma": 0.15,
        "estimate_sigma": 0.2,
        "final_test_fail_probability": 0.08,
        "stoppage_probability": 0.03,
        "stoppage_minutes": 240.0,
    },
}
POLICIES = (
    ApprovalPolicy.KEEP,
    ApprovalPolicy.FCFS,
    ApprovalPolicy.EDD,
    ApprovalPolicy.SLACK,
    ApprovalPolicy.CR,
)


@dataclass(frozen=True, slots=True)
class RunSpec:
    condition: str
    policy: str
    overtime: bool
    seed: int

    @property
    def label(self) -> str:
        return f"{self.condition}/{self.policy}{'+OT' if self.overtime else ''}/s{self.seed}"


@dataclass(frozen=True, slots=True)
class LotOutcome:
    lot_id: str
    completed_at: datetime
    gate_at: datetime
    due_at: datetime
    shipped_at: datetime
    gate_delay_minutes: float
    due_tardiness_minutes: float
    completion_working_hours: float


@dataclass(frozen=True, slots=True)
class RunRow:
    condition: str
    policy: str
    overtime: bool
    seed: int
    late_gate_lots: int
    gate_delay_minutes: float
    late_due_lots: int
    due_tardiness_minutes: float
    on_time_rate: float
    mean_completion_hours: float
    overtime_minutes: float
    approvals: int
    approved_candidates: str
    final_plan_version: int
    replan_reviews: int
    worker_estimates: int
    final_test_failures: int
    steps: int
    violations: int
    wall_seconds: float
    lot_detail: str


def plan_runs(
    *,
    reps: int,
    conditions: Sequence[str] = tuple(CONDITIONS),
    policies: Sequence[ApprovalPolicy] = POLICIES,
    first_seed: int = 1,
) -> list[RunSpec]:
    specs: list[RunSpec] = []
    for seed in range(first_seed, first_seed + reps):
        for condition in conditions:
            for policy in policies:
                for overtime in (False, True):
                    if overtime and policy is ApprovalPolicy.KEEP:
                        continue
                    specs.append(RunSpec(condition, policy.value, overtime, seed))
    return specs


def truth_for(condition: str, seed: int) -> TruthModel:
    return TruthModel(seed=seed, **CONDITIONS[condition])


def overtime_open_minutes(result: RunResult, calendar: WorkCalendar) -> float:
    """Extra operating time on approved overtime days (D078 definition).

    Per day: from the regular close (17:00) to the last work end inside the
    overtime window, i.e. how long the plant had to stay open. Idle gaps
    inside that span count, because staff are paid for staying; this is not
    the sum of busy work minutes. The candidate KPI uses the same definition.
    """

    total = 0.0
    for day in calendar.overtime_days:
        close = calendar.regular_close(day)
        window_close = calendar.closing_time(day)
        last = max(
            (
                min(record.finished_at, window_close)
                for record in result.plant.records
                if record.started_at < window_close and record.finished_at > close
            ),
            default=None,
        )
        if last is not None and last > close:
            total += (last - close).total_seconds() / 60.0
    return total


def lot_outcomes(
    result: RunResult,
    *,
    gates: dict[str, datetime],
    dues: dict[str, datetime],
    regular: WorkCalendar,
    started_at: datetime,
    inspection_lead_minutes: float = INSPECTION_LEAD_WORKING_MINUTES,
) -> list[LotOutcome]:
    completed: dict[str, datetime] = {}
    for record in result.plant.records:
        if record.process_code == "FINAL_TEST" and record.result == "PASS":
            previous = completed.get(record.lot_id)
            if previous is None or record.finished_at > previous:
                completed[record.lot_id] = record.finished_at
    outcomes = []
    for lot_id in sorted(gates):
        done = completed.get(lot_id)
        if done is None:
            # A LOT finished before the run started has no records here.
            continue
        shipped = regular.add_working_minutes(done, inspection_lead_minutes)
        outcomes.append(
            LotOutcome(
                lot_id=lot_id,
                completed_at=done,
                gate_at=gates[lot_id],
                due_at=dues[lot_id],
                shipped_at=shipped,
                gate_delay_minutes=max(0.0, (done - gates[lot_id]).total_seconds() / 60.0),
                due_tardiness_minutes=max(0.0, (shipped - dues[lot_id]).total_seconds() / 60.0),
                completion_working_hours=regular.working_minutes_between(started_at, done) / 60.0,
            )
        )
    return outcomes


def execute(spec: RunSpec) -> RunRow:
    """Run one closed loop in a private temporary database."""

    from production_control.sim.worlds import build_demo_world

    started = datetime.fromisoformat(DEMO_START_ISO)
    config = (
        replace(DEFAULT_FORECAST_CONFIG, overtime_end=OVERTIME_END)
        if spec.overtime
        else DEFAULT_FORECAST_CONFIG
    )
    clock = wall_time.perf_counter()
    with tempfile.TemporaryDirectory(prefix="pc-exp-") as tmp:
        database = build_demo_world(Path(tmp) / "world.db", baseline_lot_order=BASELINE_LOT_ORDER)
        harness = build_harness(
            database,
            truth=truth_for(spec.condition, spec.seed),
            start_time=started,
            run_tag=spec.label,
            forecast_config=config,
        )
        regular = replace(harness.plant.calendar, overtime=())
        gates = {
            gate["lot_id"]: datetime.fromisoformat(gate["planned_at"])
            for gate in harness.terminal.gates()
            if gate["gate_type"] == "SHIPPING_INSPECTION"
        }
        dues = {
            lot["lot_id"]: datetime.fromisoformat(lot["due_at"]) for lot in harness.terminal.lots()
        }
        result = harness.run(ApprovalPolicy(spec.policy))
        outcomes = lot_outcomes(result, gates=gates, dues=dues, regular=regular, started_at=started)
        overtime = overtime_open_minutes(result, harness.plant.calendar)
    return RunRow(
        condition=spec.condition,
        policy=spec.policy,
        overtime=spec.overtime,
        seed=spec.seed,
        late_gate_lots=sum(1 for item in outcomes if item.gate_delay_minutes > 0),
        gate_delay_minutes=sum(item.gate_delay_minutes for item in outcomes),
        late_due_lots=sum(1 for item in outcomes if item.due_tardiness_minutes > 0),
        due_tardiness_minutes=sum(item.due_tardiness_minutes for item in outcomes),
        on_time_rate=(
            sum(1 for item in outcomes if item.due_tardiness_minutes == 0) / len(outcomes)
            if outcomes
            else float("nan")
        ),
        mean_completion_hours=(
            mean(item.completion_working_hours for item in outcomes) if outcomes else float("nan")
        ),
        overtime_minutes=overtime,
        approvals=len(result.approvals),
        approved_candidates=";".join(
            f"{item.at.isoformat()}={item.candidate_id}" for item in result.approvals
        ),
        final_plan_version=result.final_plan_version,
        replan_reviews=sum(1 for item in result.reviews if item.risk == "URGENT"),
        worker_estimates=len(result.estimates),
        final_test_failures=sum(1 for record in result.plant.records if record.result == "FAIL"),
        steps=result.steps,
        violations=len(result.violations),
        wall_seconds=round(wall_time.perf_counter() - clock, 2),
        lot_detail=json.dumps(
            [
                {
                    "lot_id": item.lot_id,
                    "completed_at": item.completed_at.isoformat(),
                    "gate_at": item.gate_at.isoformat(),
                    "shipped_at": item.shipped_at.isoformat(),
                    "due_at": item.due_at.isoformat(),
                }
                for item in outcomes
            ]
        ),
    )


# ---------------------------------------------------------------- summary
SUMMARY_METRICS = (
    "late_gate_lots",
    "gate_delay_minutes",
    "late_due_lots",
    "due_tardiness_minutes",
    "on_time_rate",
    "mean_completion_hours",
    "overtime_minutes",
    "approvals",
)


def _t_quantile_975(df: int) -> float:
    """Two-sided 95% Student-t quantile (small table, normal beyond 30)."""

    table = {
        1: 12.706, 2: 4.303, 3: 3.182, 4: 2.776, 5: 2.571, 6: 2.447, 7: 2.365,
        8: 2.306, 9: 2.262, 10: 2.228, 11: 2.201, 12: 2.179, 13: 2.160, 14: 2.145,
        15: 2.131, 16: 2.120, 17: 2.110, 18: 2.101, 19: 2.093, 20: 2.086, 21: 2.080,
        22: 2.074, 23: 2.069, 24: 2.064, 25: 2.060, 26: 2.056, 27: 2.052, 28: 2.048,
        29: 2.045, 30: 2.042,
    }  # fmt: skip
    return table.get(df, NormalDist().inv_cdf(0.975))


def mean_ci(values: Sequence[float]) -> tuple[float, float]:
    """Mean and 95% confidence half-width."""

    if not values:
        return float("nan"), float("nan")
    if len(values) == 1:
        return float(values[0]), float("nan")
    return mean(values), _t_quantile_975(len(values) - 1) * stdev(values) / math.sqrt(len(values))


def summarise(rows: Iterable[RunRow]) -> list[dict[str, object]]:
    """Per configuration mean +/- 95% CI, and paired differences vs KEEP."""

    rows = list(rows)
    keep = {
        (row.condition, row.seed): row
        for row in rows
        if row.policy == ApprovalPolicy.KEEP.value and not row.overtime
    }
    groups: dict[tuple[str, str, bool], list[RunRow]] = {}
    for row in rows:
        groups.setdefault((row.condition, row.policy, row.overtime), []).append(row)

    summary: list[dict[str, object]] = []
    for (condition, policy, overtime), members in sorted(groups.items()):
        entry: dict[str, object] = {
            "condition": condition,
            "policy": policy + ("+OT" if overtime else ""),
            "n": len(members),
        }
        for metric in SUMMARY_METRICS:
            value, half = mean_ci([float(getattr(row, metric)) for row in members])
            entry[f"{metric}_mean"] = round(value, 3)
            entry[f"{metric}_ci95"] = round(half, 3) if not math.isnan(half) else ""
        for metric in ("gate_delay_minutes", "due_tardiness_minutes"):
            diffs = [
                float(getattr(row, metric)) - float(getattr(keep[(condition, row.seed)], metric))
                for row in members
                if (condition, row.seed) in keep
            ]
            value, half = mean_ci(diffs)
            entry[f"{metric}_vs_keep_mean"] = round(value, 3) if diffs else ""
            entry[f"{metric}_vs_keep_ci95"] = (
                round(half, 3) if diffs and not math.isnan(half) else ""
            )
        entry["violations"] = sum(row.violations for row in members)
        summary.append(entry)
    return summary


def _write_csv(path: Path, rows: list[dict[str, object]]) -> None:
    if not rows:
        return
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


def _git_commit() -> str:
    try:
        return subprocess.run(
            ["git", "rev-parse", "HEAD"], capture_output=True, text=True, check=True
        ).stdout.strip()
    except (OSError, subprocess.CalledProcessError):
        return "unknown"


def run_experiment(
    specs: Sequence[RunSpec],
    *,
    out: Path,
    workers: int,
    progress: bool = True,
) -> list[RunRow]:
    out.mkdir(parents=True, exist_ok=True)
    started = wall_time.perf_counter()
    # Each finished run is appended to runs.jsonl at once, so an interrupted
    # experiment resumes where it stopped and never repeats a finished run.
    journal = out / "runs.jsonl"
    done: dict[RunSpec, RunRow] = {}
    if journal.exists():
        for line in journal.read_text(encoding="utf-8").splitlines():
            if line.strip():
                row = RunRow(**json.loads(line))
                done[RunSpec(row.condition, row.policy, row.overtime, row.seed)] = row
    todo = [spec for spec in specs if spec not in done]
    rows: list[RunRow] = [done[spec] for spec in specs if spec in done]
    if progress and done:
        print(f"resuming: {len(rows)} of {len(specs)} runs already finished", flush=True)
    failures: list[dict[str, object]] = []

    def record(row: RunRow, handle) -> None:
        rows.append(row)
        handle.write(json.dumps(asdict(row)) + "\n")
        handle.flush()
        if progress:
            print(
                f"[{len(rows)}/{len(specs)}] {row.condition}/{row.policy}"
                f"{'+OT' if row.overtime else ''}/s{row.seed} "
                f"gate_delay={row.gate_delay_minutes:.0f} "
                f"due_tardy={row.due_tardiness_minutes:.0f} "
                f"ot={row.overtime_minutes:.0f} ({row.wall_seconds:.0f}s)",
                flush=True,
            )

    def fail(spec: RunSpec, error: BaseException) -> None:
        # A failed run is a finding, not noise: it is written down and the
        # experiment exits non-zero, but the remaining runs still execute.
        failures.append({**asdict(spec), "error": f"{type(error).__name__}: {error}"})
        if progress:
            print(f"FAILED {spec.label}: {error}", flush=True)

    with journal.open("a", encoding="utf-8") as handle:
        if workers <= 1:
            for spec in todo:
                try:
                    row = execute(spec)
                except Exception as error:
                    fail(spec, error)
                else:
                    record(row, handle)
        else:
            with ProcessPoolExecutor(max_workers=workers) as pool:
                futures = {pool.submit(execute, spec): spec for spec in todo}
                for future in as_completed(futures):
                    try:
                        row = future.result()
                    except Exception as error:
                        fail(futures[future], error)
                    else:
                        record(row, handle)

    (out / "failures.json").write_text(json.dumps(failures, indent=2), encoding="utf-8")
    order = {spec: index for index, spec in enumerate(specs)}
    rows.sort(key=lambda row: order[RunSpec(row.condition, row.policy, row.overtime, row.seed)])
    _write_csv(out / "runs.csv", [asdict(row) for row in rows])
    _write_csv(out / "summary.csv", summarise(rows))
    (out / "config.json").write_text(
        json.dumps(
            {
                "start": DEMO_START_ISO,
                "baseline_lot_order": BASELINE_LOT_ORDER,
                "conditions": CONDITIONS,
                "policies": [policy.value for policy in POLICIES],
                "overtime_end": OVERTIME_END.isoformat(),
                "inspection_lead_working_minutes": INSPECTION_LEAD_WORKING_MINUTES,
                "forecast_config": {
                    "calendar_id": DEFAULT_FORECAST_CONFIG.calendar_id,
                    "pace_min_samples": DEFAULT_FORECAST_CONFIG.pace_min_samples,
                    "warning_threshold_minutes": DEFAULT_FORECAST_CONFIG.warning_threshold_minutes,
                },
                "seeds": sorted({spec.seed for spec in specs}),
                "runs": len(specs),
                "git_commit": _git_commit(),
                "python": sys.version.split()[0],
                "platform": platform.platform(),
                "wall_seconds": round(wall_time.perf_counter() - started, 1),
            },
            indent=2,
        ),
        encoding="utf-8",
    )
    return rows


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument(
        "--reps", type=int, default=10, help="replications (seeds) per configuration"
    )
    parser.add_argument("--first-seed", type=int, default=1)
    parser.add_argument(
        "--conditions", nargs="+", default=list(CONDITIONS), choices=list(CONDITIONS)
    )
    parser.add_argument(
        "--policies", nargs="+", default=[policy.value for policy in POLICIES],
        choices=[policy.value for policy in POLICIES],
    )  # fmt: skip
    parser.add_argument("--workers", type=int, default=os.cpu_count() or 1)
    parser.add_argument("--out", type=Path, default=Path("experiments/latest"))
    args = parser.parse_args(argv)

    specs = plan_runs(
        reps=args.reps,
        conditions=args.conditions,
        policies=[ApprovalPolicy(value) for value in args.policies],
        first_seed=args.first_seed,
    )
    rows = run_experiment(specs, out=args.out, workers=args.workers)
    violations = sum(row.violations for row in rows)
    failures = json.loads((args.out / "failures.json").read_text(encoding="utf-8"))
    print(
        f"{len(rows)} runs written to {args.out} "
        f"({violations} plant violations, {len(failures)} failed runs)"
    )
    return 1 if violations or failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
