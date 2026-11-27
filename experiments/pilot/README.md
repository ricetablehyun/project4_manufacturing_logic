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
- Final due tardiness assumes 3 working days of shipping inspection after the
  last FINAL_TEST pass. Shipping-inspection entry delay uses the Gate's
  planned start and needs no assumption.

This is the pilot used to check the experiment before the 30-replication run;
the presentation uses the 30-replication results.
