# LOT / InspectionGate management API contract

Decision references: D058, D059.

This slice closes the remaining FastAPI Milestone 5 management scope without
turning already-materialized production data into unrestricted CRUD.

## LOT endpoints

### `GET /lots`

Returns all existing LOTs in stable `lot_id` order.

Each item exposes:

- `lot_id`
- `product_id`
- `lot_code`
- `quantity`
- `release_at`
- `due_at`
- `status`
- `created_at`

### `PATCH /lots/{lot_id}`

Only these fields are mutable in D059:

- `release_at`
- `due_at`
- `status`

`release_at` and `due_at` must be timezone-aware. `status` must be a non-empty
string. This slice does not invent a new LOT status-transition policy.

Structural/materialization fields such as `lot_id`, `product_id`, `lot_code`,
and `quantity` are not accepted by the patch model. Extra fields are rejected
with `422` rather than silently ignored.

A missing LOT returns `404`.

## InspectionGate endpoints

### `GET /inspection-gates`

Returns all existing inspection gates in stable `gate_id` order.

Optional query parameter:

- `lot_id` — return only gates belonging to that LOT.

Each item exposes:

- `gate_id`
- `lot_id`
- `gate_type`
- `required_after_step_id`
- `planned_at`
- `completed_at`
- `status`

### `PATCH /inspection-gates/{gate_id}`

Only these fields are mutable in D059:

- `planned_at`
- `completed_at`
- `status`

`planned_at` must be timezone-aware and may not be null. `completed_at` may be
set to a timezone-aware value or explicitly cleared with `null`. `status` must
be a non-empty string. This slice does not invent a new gate status-transition
policy.

Structural fields such as `gate_id`, `lot_id`, `gate_type`, and
`required_after_step_id` are not accepted. Extra fields return `422`.

A missing gate returns `404`.

## Why full CRUD is intentionally excluded

LOT quantity is already coupled to materialized Unit / UnitOperation rows.
Changing `quantity` independently could make the LOT header disagree with the
actual execution entities. New LOT creation likewise needs a coordinated
workflow covering routing selection, Unit materialization, initial gates, and
initial-plan behavior.

Those workflows require a separate design decision and are not implied by a
simple CRUD endpoint.

## Persistence boundary

The FastAPI routes remain thin and delegate reads/updates to
`production_control.persistence.admin_management`. The service updates only the
D059-approved mutable columns and commits the existing row; it does not create
or delete LOTs, gates, Units, operations, or plans.
