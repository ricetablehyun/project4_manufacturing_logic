# Replan Approval API contract

Decision reference: D057.

## Endpoint

`POST /replan-approvals`

The client selects one transient D056 candidate, but does not send KPI or task
values back to the server. The server recomputes the candidate from persisted
production state and only persists the server-side result.

## Request

```json
{
  "parent_plan_id": "PLAN-2",
  "candidate_id": "EDD",
  "candidate_as_of": "2026-10-05T10:00:00+09:00"
}
```

- `parent_plan_id` identifies the approved plan from which the candidate was
  originally viewed.
- `candidate_id` is one of the currently recomputed transient candidate IDs.
- `candidate_as_of` must be timezone-aware and is the same snapshot time used
  when the manager reviewed the candidate.
- KPI values, target times, quantities, and priority ranks are intentionally not
  accepted from the client.

## Server-side stale-safety flow

1. Confirm `parent_plan_id` is still the current approved plan.
2. Recompute D056 candidates at `candidate_as_of`.
3. Reuse Live Forecast time-travel validation. If a persisted WorkEvent is newer
   than `candidate_as_of`, reject the approval as stale.
4. Require the recomputed policy action to remain `GENERATE_CANDIDATES`.
5. Select `candidate_id` from the recomputed server-side candidates.
6. Convert that candidate's KPI/tasks into explicit approval drafts.
7. Delegate persistence to the existing `persist_approved_replan()` lifecycle.
8. Generate the new plan ID, task IDs, and approval timestamp on the server.

The endpoint never auto-approves the recommended candidate. A manager selection
is required.

## Response

```json
{
  "plan_id": "REPLAN-...",
  "version": 3,
  "status": "APPROVED",
  "parent_plan_id": "PLAN-2",
  "priority_rule": "EDD",
  "approved_at": "2026-09-28T00:50:00+00:00",
  "selected_candidate_id": "EDD"
}
```

A successful approval creates the next official SchedulePlan version. Because
Live Forecast resolves the latest approved version, subsequent `GET /forecast`
requests use the newly approved plan automatically.

## Status behavior

- `201 Created` — candidate recomputed and persisted as the new approved plan.
- `404 Not Found` — requested `candidate_id` is absent from the recomputed
  candidate set.
- `409 Conflict` — parent plan is stale, execution state is newer than the
  candidate snapshot, Live Forecast is WAIT, or policy no longer generates
  candidates.
- `422 Unprocessable Content` — request validation fails, including timezone-naive
  `candidate_as_of`.
- `503 Service Unavailable` — Forecast/replan application configuration was not
  supplied to the API app factory.

## Persistence boundary

Only the selected candidate is persisted. Historical approved plans remain
`APPROVED`; current-plan identity continues to be the highest approved version.
Transient FCFS / EDD / Slack / CR candidates remain outside persistence.

The approval trigger stored in the new plan is derived from the recomputed risk
level rather than supplied by the client.
