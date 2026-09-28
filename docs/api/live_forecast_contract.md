# Live Forecast API contract

Decision references: D054, D055.

## Endpoint

`GET /forecast`

The endpoint calculates the current Live Forecast for every LOT represented by
the latest approved `SchedulePlan`. It does not persist a forecast snapshot.

### Query

- `as_of` — optional timezone-aware ISO 8601 datetime.
- When omitted, the server current time is used.
- When supplied, the current persisted execution state is projected from that
  reference time. V1 does not reconstruct a historical state older than already
  persisted WorkEvents.

### Application configuration

The API does not hard-code project policy values that were confirmed as
configurable parameters. `LiveForecastConfig` supplies:

- `calendar_id`
- `pace_min_samples`
- `warning_threshold_minutes`

## Success response

```json
{
  "plan_id": "PLAN-2",
  "plan_version": 2,
  "as_of": "2026-10-05T10:00:00+09:00",
  "readiness": "READY",
  "lots": [
    {
      "lot_id": "LOT-101",
      "forecast_end": "2026-10-05T15:00:00+09:00",
      "risk_level": "WARNING"
    }
  ],
  "gates": [
    {
      "gate_id": "GATE-LOT-101-SHIPPING-INSPECTION",
      "lot_id": "LOT-101",
      "required_after_step_id": "STEP-06-FINAL-TEST",
      "gate_type": "SHIPPING_INSPECTION",
      "planned_at": "2026-10-05T15:30:00+09:00",
      "forecast_at": "2026-10-05T15:00:00+09:00",
      "slack_minutes": 30.0,
      "risk_level": "WARNING"
    }
  ],
  "processes": [
    {
      "lot_id": "LOT-101",
      "process_code": "TUNING",
      "forecast_start": "2026-10-05T11:00:00+09:00",
      "forecast_end": "2026-10-05T13:00:00+09:00",
      "scheduled_operation_count": 4
    }
  ],
  "missing_gate_ids": [],
  "waiting_operation_ids": []
}
```

`waiting_operation_ids` exposes an explicit D043 Forecast WAIT condition, such
as a RUNNING operation that exceeded its current Pace without a worker-entered
remaining-time estimate. `missing_gate_ids` exposes Gate requirements whose
forecast timestamp cannot yet be resolved.

## Status behavior

- `200 OK` — Forecast calculated or returned in explicit `WAIT` readiness.
- `422 Unprocessable Entity` — `as_of` is not timezone-aware or FastAPI query
  validation fails.
- `409 Conflict` — the current persisted/approved-plan state cannot be
  consistently projected, for example a missing approved plan mapping or an
  `as_of` older than the latest persisted WorkEvent.
- `503 Service Unavailable` — Live Forecast application configuration was not
  supplied to the API app factory.

## Implementation boundary

The endpoint is a transport boundary only. It reuses the persisted Pace input
builder, approved-plan dispatch adapter, event-driven finite-capacity scheduler,
and persisted Gate/LOT risk evaluator. Production rules are not duplicated in
the FastAPI layer.
