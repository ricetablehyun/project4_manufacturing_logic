# Pilot experiment (10 replications)

Reproduce:

```
python -m production_control.sim.experiment --reps 10 --out experiments/pilot
```

- Code: commit `88743464` (identical source to `main` after PR #47). The first
  79 runs were produced before PR #47; the fix only changes a path that
  previously aborted with HTTP 409, so those runs are unaffected.
- 270 runs = 3 conditions x (KEEP + 4 rules x overtime off/on) x seeds 1-10.
  0 plant violations, 0 failed runs (`failures.json`).
- Files: `runs.csv` (one row per run), `summary.csv` (mean, 95% CI, paired
  difference vs KEEP per condition), `config.json` (parameters, commit),
  `runs.jsonl` (resume journal).
- Final due tardiness now uses the system's shipping-inspection rule (see
  `experiments/main30/README.md`); the fields were re-derived from `lot_detail`.
  Shipping-inspection entry delay uses the Gate's planned start and needs no
  assumption.

This is the pilot used to check the experiment before the 30-replication run;
the presentation uses the 30-replication results.

## Terms (updated after review)

- `STOPPAGE_REWORK` was recorded as `HOLD_REWORK`; only the label changed.
  It is a delay model: 3% of attempts need 240 more working minutes while the
  operation stays RUNNING. No HOLD / RESUME events are sent, so these results
  test replanning under extra delay, not HOLD event handling. The random draws
  are unchanged (same key), and re-summarising `runs.jsonl` reproduces
  `summary.csv` exactly.
- `overtime_minutes` is extra operating time: per overtime day, from 17:00 to
  the last work end in the window, idle gaps included. It is not the sum of
  busy work minutes.
- The virtual terminal used FastAPI's in-process TestClient. Real-socket
  operation is covered by `tests/integration/test_closed_loop_over_network.py`
  (uvicorn + httpx on localhost). The Pico 2 WH hardware is not integrated.
- Final due tardiness assumes inspection follows the system rule exactly (no
  queue, failure or slip). It is an assumption, not measured data;
  shipping-inspection entry delay needs no assumption.
