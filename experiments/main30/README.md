# Main experiment (30 replications)

Reproduce (about 3 hours of runtime with 4 workers; it resumes from `runs.jsonl` if interrupted):

```
python -m production_control.sim.experiment --reps 30 --workers 4 --out experiments/main30
```

- 810 runs = 3 conditions x (KEEP + 4 rules x overtime off/on) x seeds 1-30.
  Final state: 0 plant violations, 0 failed runs (`failures.json`).
- Start state: the midterm demo at 2026-10-22 13:00, with an FCFS baseline plan
  (LOT-101, LOT-102, LOT-103). Parameters are in `config.json`.
- Seeds 1-10 are the pilot's runs (`experiments/pilot`), reused unchanged.
- Files: `runs.csv` (one row per run), `summary.csv` (mean, 95% Student-t CI,
  paired difference vs KEEP on the same seed), `config.json`, `runs.jsonl`
  (resume journal). `config.json`'s `git_commit` and `wall_seconds` describe the
  last resume only.

## Three failed runs and the fix

The first pass finished 807 of 810 runs. Three failed with HTTP 409 on
`/replan-candidates` (`failures_before_3a7ff6e.json`): STOPPAGE_REWORK FCFS
seed 13 (overtime off and on) and STOPPAGE_REWORK CR seed 21.

Cause: a replanning decision at exactly 17:00 found an operation still RUNNING.
The plant pauses work at close and resumes it the next morning, but the event
scheduler required RUNNING work to restart at the decision time itself.
Commit `3a7ff6e` makes it expect the first working moment from the decision time.
During working hours that is the decision time itself, so every schedule that
did not fail before is unchanged. A regression test covers the case
(`test_running_work_paused_at_closing_time_resumes_next_opening`).

Checks: the three runs were re-run on `3a7ff6e` and completed with 0
violations. Two earlier runs re-run on `3a7ff6e` (STOPPAGE_REWORK CR+OT seed 20,
NORMAL EDD+OT seed 5) reproduced their journal rows field for field, except wall time.

## Results (shipping-inspection entry delay, minutes, mean ± 95% CI, n = 30)

| Condition | KEEP | FCFS | FCFS+OT | EDD | EDD+OT | SLACK | SLACK+OT | CR | CR+OT |
|---|---|---|---|---|---|---|---|---|---|
| NORMAL | 190.3 ± 13.4 | 189.5 ± 13.3 | 118.0 ± 37.7 | 0 | 0 | 0 | 0 | 34.3 ± 8.8 | 19.5 ± 8.6 |
| SLOW | 1522.9 ± 15.8 | 1476.2 ± 72.8 | 868.2 ± 235.9 | 0 | 0 | 1.3 ± 2.7 | 0 | 69.6 ± 20.0 | 18.6 ± 10.3 |
| STOPPAGE_REWORK | 2432.5 ± 578.8 | 2329.3 ± 463.7 | 1801.3 ± 322.8 | 14.6 ± 13.6 | 0.7 ± 1.2 | 90.8 ± 110.3 | 5.4 ± 9.7 | 117.1 ± 49.1 | 71.7 ± 34.7 |

What the data supports:

- Replanning with EDD or SLACK removes the entry delay that keeping the plan
  leaves. In NORMAL and SLOW, EDD has 0 delay in all 30 runs. In
  STOPPAGE_REWORK, EDD is late in 5 of 30 runs and SLACK in 10 of 30.
- FCFS without overtime is close to KEEP (NORMAL paired difference −0.9 ± 1.6),
  as expected, because the baseline plan is already in FCFS order. This is a
  sanity check, not an improvement.
- Overtime lowers delay where a rule leaves delay: CR, FCFS, and EDD/SLACK in
  STOPPAGE_REWORK. Overtime is extra operating time (17:00 to the last work end in
  the window, idle gaps included); see `overtime_minutes_mean` in `summary.csv`.
- Limitation: in NORMAL, EDD+OT and SLACK+OT open 108 minutes of overtime on
  average (27 of 30 runs use some) with no delay to remove, because EDD alone is
  already at 0. The forecast at decision time is more pessimistic than what
  happens later. The policy chooses on the forecast, so it buys overtime that
  turns out unnecessary.
- CR re-approves often (3.2-4.3 approvals per run versus 1-2 for EDD/SLACK).
- Final due tardiness (with the 3-working-day inspection assumption below)
  appears only in STOPPAGE_REWORK KEEP (72.9 ± 103.6, in 2 of 30 runs) and FCFS
  (36.5 ± 74.7, in 1 of 30 runs). Both CIs include 0. This is a rare-event
  observation, not a significant difference.

## Terms and assumptions

- `STOPPAGE_REWORK` is a delay model: 3% of attempts need 240 more working
  minutes while the operation stays RUNNING, and 8% of FINAL_TEST attempts fail
  and are reworked. No HOLD / RESUME events are sent.
- Shipping-inspection entry delay = completion of the LOT's last FINAL_TEST pass
  minus `InspectionGate.planned_at`, in wall-clock minutes. It needs no assumption.
- Final due tardiness assumes shipping inspection and dispatch take exactly 3
  working days after the last FINAL_TEST pass, for every LOT, with no queue. It is
  an assumption, not measured data.
- The virtual terminal uses FastAPI's in-process TestClient. Real-socket
  operation is covered by `tests/integration/test_closed_loop_over_network.py`.
  The Pico 2 WH hardware is not integrated.
