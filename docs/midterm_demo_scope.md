# Midterm demo scope

The midterm milestone demonstrates the software closed loop before the Pico terminal is connected.

## In scope

1. LOT-first Production Overview
2. Shop-floor WorkEvent input from Streamlit
3. Live Forecast and Gate/due-date risk refresh
4. FCFS / EDD / Slack / CR replanning candidate comparison
5. Manager approval of one candidate
6. New Approved Plan reflected by the next Forecast

## Production Overview hierarchy

Inside each LOT, the dashboard is process-first rather than Unit-first:

1. LOT due date / Forecast completion / risk
2. compact per-process completion progress
3. process-grouped Unit states: completed / running / hold / waiting
4. process Forecast and inspection schedule only inside LOT detail

This avoids a flat Unit table that repeats the current process for every Unit and makes process WIP easier to inspect.

## Demo identifiers

- operator-facing LOT codes start from `LOT-001`, `LOT-002`, ...
- Unit codes are global sequential production numbers and do not reset at each LOT boundary
- the current two-LOT demo therefore shows `U001` through `U008`
- persistence primary keys stay unchanged; these shop-floor codes are presentation/business identifiers

## Quality inspection schedule semantics

- the shipping-inspection start time is a quality-team-notified schedule input
- internal production must be complete before that inspection start time
- shipping inspection lasts 3 business days, excluding Saturday and Sunday
- the inspection start day counts as business day 1; e.g. Monday start -> Wednesday 17:00 expected finish
- the demo due dates are illustrative dates after inspection completion, not an automatic production rule
- dashboard Gate slack means `quality inspection start - internal production Forecast completion`

## Input boundary

- WorkEvent input (`START`, `HOLD`, `RESUME`, `COMPLETE`, `PASS`, `FAIL`) is available from the Streamlit operator tab for the midterm demo.
- Due-date and inspection-schedule administration already has API-side boundaries, but dedicated administrator input UI is deferred until the production-status screen is settled.

## Out of scope for this milestone

- Pico 2 WH hardware input
- New scheduling algorithms
- Facility-layout optimization
- Calendar/Resource management UI
- Production authentication/authorization

The demo runtime is localhost-only. FastAPI and Streamlit must bind to `127.0.0.1`; no router port forwarding or public firewall exception is required.
