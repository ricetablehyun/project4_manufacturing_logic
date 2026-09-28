# Midterm demo scope

The midterm milestone demonstrates the software closed loop before the Pico terminal is connected.

## In scope

1. Production Overview
2. Shop-floor WorkEvent input from Streamlit
3. Live Forecast and Gate/due-date risk refresh
4. FCFS / EDD / Slack / CR replanning candidate comparison
5. Manager approval of one candidate
6. New Approved Plan reflected by the next Forecast

## Out of scope for this milestone

- Pico 2 WH hardware input
- New scheduling algorithms
- Facility-layout optimization
- Calendar/Resource management UI
- Production authentication/authorization

The demo runtime is localhost-only. FastAPI and Streamlit must bind to `127.0.0.1`; no router port forwarding or public firewall exception is required.
