# Local demo security boundary

This repository's midterm demo is intentionally local-only.

- FastAPI binds to `127.0.0.1:8000`.
- Streamlit binds to `127.0.0.1`.
- Do not use `0.0.0.0` for the demo.
- Do not configure router port forwarding.
- Do not add public firewall exceptions.
- The current demo does not claim production authentication, authorization, TLS, rate limiting, or device identity.

The implemented API still validates transport payloads and preserves server-side state-transition and stale-replan checks. Production security is a later milestone, not part of the local midterm demo.
