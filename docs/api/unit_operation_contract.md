# UnitOperation read API contract

## Purpose

The midterm operator UI and the later Pico terminal need a read-only way to discover the current persisted UnitOperation without reading SQLite directly.

## Endpoint

`GET /unit-operations`

Optional query parameter:

- `lot_id`: restrict rows to one LOT.

## Response fields

- `operation_id`
- `lot_id`
- `unit_id`
- `unit_code`
- `routing_step_id`
- `seq_no`
- `process_code`
- `state`
- `eligible_at`
- `attempt_no`
- `active_minutes`
- `result`
- `last_event_at`

Rows are deterministic by LOT, Unit, and RoutingStep sequence.

## Boundary

This endpoint is read-only. It does not calculate a new execution state and does not mutate planning data. WorkEvent validity remains enforced by the existing `POST /work-events` server path.
