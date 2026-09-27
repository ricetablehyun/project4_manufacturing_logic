# WorkEvent API contract (V1)

This document records the first FastAPI vertical slice selected for Milestone 5.

## Endpoint

`POST /work-events`

The request body is self-contained so the same payload can be persisted/retried by a Pico client.

## Request

```json
{
  "event_id": "E-20260928-0001",
  "unit_operation_id": "OP1",
  "event_type": "START",
  "occurred_at": "2026-09-28T08:30:00+09:00",
  "station_code": "TUNING",
  "worker_code": "WORKER-A",
  "reason": null
}
```

`event_type` uses the existing execution-domain values: `START`, `HOLD`, `RESUME`, `COMPLETE`, `PASS`, `FAIL`.

`occurred_at` must include a timezone offset.

## Success response

```json
{
  "event_id": "E-20260928-0001",
  "duplicate": false,
  "operation_id": "OP1",
  "lot_id": "L1",
  "unit_id": "U1",
  "process_code": "TUNING",
  "state": "RUNNING",
  "attempt_no": 1,
  "active_minutes": 0.0,
  "result": null
}
```

## HTTP semantics

- new accepted WorkEvent: `201 Created`
- retry of the same persisted `event_id`: `200 OK` with `duplicate=true`
- unknown `unit_operation_id`: `404 Not Found`
- domain/state conflict such as HOLD while WAITING: `409 Conflict`
- request-schema validation failure such as a timezone-naive `occurred_at`: `422 Unprocessable Entity`

## Boundary

The API layer must not duplicate production rules. It validates the transport schema and delegates execution-state/idempotency/rework behavior to the existing `persist_work_event()` service.

Deployment-time database path/configuration is intentionally not decided in this slice. `create_app(session_factory=...)` receives the persistence dependency from outside.
