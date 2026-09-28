# Replan Candidate API contract

Decision reference: D056.

## Endpoint

`POST /replan-candidates`

The endpoint evaluates the current persisted production state and, only when the
confirmed replanning policy reports `URGENT`, calculates the four V1 dispatching
candidates:

- `FCFS`
- `EDD`
- `SLACK`
- `CR`

Candidates are calculation results only. This endpoint does **not** insert or
update `SchedulePlan` / `ScheduleTask` rows and never auto-applies a candidate.
Manager approval remains a separate API/application boundary.

## Query

- `as_of` — optional timezone-aware ISO 8601 datetime.
- When omitted, server current time is used.
- The same current-state time-travel restriction as `GET /forecast` applies.

## Response

```json
{
  "parent_plan_id": "PLAN-2",
  "parent_plan_version": 2,
  "as_of": "2026-10-05T10:00:00+09:00",
  "risk_level": "URGENT",
  "action": "GENERATE_CANDIDATES",
  "recommended_candidate_id": "CR",
  "requires_manager_approval": true,
  "candidates": [
    {
      "candidate_id": "FCFS",
      "rule": "FCFS",
      "kpi": {
        "late_lot_count": 2,
        "total_tardiness_minutes": 180.0,
        "overtime_minutes": 0.0,
        "change_count": 5
      },
      "tasks": [
        {
          "lot_id": "LOT-101",
          "routing_step_id": "STEP-04-TUNING",
          "target_start": "2026-10-05T10:00:00+09:00",
          "target_end": "2026-10-05T11:40:00+09:00",
          "target_qty": 4,
          "priority_rank": 1
        }
      ]
    }
  ]
}
```

`tasks` are LOT × RoutingStep projections of the temporary Unit-level candidate
schedule. Their priority ranks are projected from the candidate scheduler's
actual first-dispatch order into the rank slots of the current approved plan.
This preserves the existing persisted rank scale instead of inventing a new
rank numbering policy.

## Replanning boundary

- `NORMAL` → current plan is kept; `candidates=[]`.
- `WARNING` → monitoring/Forecast update only; `candidates=[]`.
- `URGENT` → calculate all four confirmed candidate rules and return the D029
  recommendation.
- Live Forecast `WAIT` → candidate generation is rejected because the confirmed
  replanning boundary requires a READY forecast.

The D029 comparison order remains:

1. late LOT count
2. total tardiness minutes
3. overtime minutes
4. priority change count

Exact KPI ties preserve the existing FCFS → EDD → SLACK → CR caller order.

## Current V1 limitation

The current scheduler only schedules inside the normal `WorkCalendar`; this API
slice does not add CalendarException/overtime capacity. Therefore candidate
`overtime_minutes` remains `0.0` until that separate production-policy slice is
implemented.

For URGENT immediate replanning, D024's Frozen Horizon exception is treated as
released for the active candidate comparison set. No candidate is persisted by
this endpoint.

## Status behavior

- `200 OK` — policy evaluated successfully, with zero or four candidates.
- `422 Unprocessable Content` — `as_of` is timezone-naive or query validation
  fails.
- `409 Conflict` — the persisted/forecast state cannot produce a consistent
  candidate calculation, including Live Forecast WAIT.
- `503 Service Unavailable` — Forecast/replanning application configuration was
  not supplied to the API app factory.
