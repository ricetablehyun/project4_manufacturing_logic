"""Virtual shop-floor terminal and manager console over the real HTTP API.

The terminal plays the role the Pico 2 WH terminal was designed for: it asks
the server for work orders, reports START / COMPLETE / PASS / FAIL events, and
answers the Pace-overrun question with the worker's expected remaining time.
It talks only to the public FastAPI endpoints, so the same code works against
an in-process ``TestClient`` or a running uvicorn server (``httpx.Client``).
"""

from dataclasses import dataclass
from datetime import datetime
from typing import Any, Protocol


class HttpClient(Protocol):
    def get(self, url: str, **kwargs: Any) -> Any: ...

    def post(self, url: str, **kwargs: Any) -> Any: ...

    def patch(self, url: str, **kwargs: Any) -> Any: ...


class TerminalError(RuntimeError):
    """The server rejected a request the virtual shop floor relied on."""


@dataclass
class CallCounter:
    work_orders: int = 0
    work_events: int = 0
    duplicate_events: int = 0
    estimates: int = 0
    forecasts: int = 0
    candidate_calculations: int = 0
    approvals: int = 0


class ShopFloorTerminal:
    def __init__(
        self,
        client: HttpClient,
        *,
        run_tag: str,
        worker_code: str = "SIM-WORKER",
        resend_every: int = 0,
    ) -> None:
        """``resend_every`` > 0 re-sends every n-th WorkEvent once more, as a
        terminal does when the server's acknowledgement is lost. The server must
        recognise the repeated event id and leave production state unchanged."""

        if not run_tag:
            raise ValueError("run_tag must not be empty")
        if resend_every < 0:
            raise ValueError("resend_every must be 0 or greater")
        self.client = client
        self.run_tag = run_tag
        self.worker_code = worker_code
        self.resend_every = resend_every
        self.calls = CallCounter()

    @staticmethod
    def _json(response: Any, *, expected: tuple[int, ...], action: str) -> Any:
        if response.status_code not in expected:
            raise TerminalError(
                f"{action} failed with HTTP {response.status_code}: {response.text}"
            )
        return response.json()

    # --------------------------------------------------------------- reads
    def work_orders(self, as_of: datetime) -> dict:
        self.calls.work_orders += 1
        response = self.client.get("/work-orders", params={"as_of": as_of.isoformat()})
        return self._json(response, expected=(200,), action="GET /work-orders")

    def forecast(self, as_of: datetime) -> dict:
        self.calls.forecasts += 1
        response = self.client.get("/forecast", params={"as_of": as_of.isoformat()})
        return self._json(response, expected=(200,), action="GET /forecast")

    def unit_operations(self) -> list[dict]:
        response = self.client.get("/unit-operations")
        return self._json(response, expected=(200,), action="GET /unit-operations")

    def current_plan(self) -> dict:
        response = self.client.get("/schedule-plan/current")
        return self._json(response, expected=(200,), action="GET /schedule-plan/current")

    def lots(self) -> list[dict]:
        response = self.client.get("/lots")
        return self._json(response, expected=(200,), action="GET /lots")

    def gates(self) -> list[dict]:
        response = self.client.get("/inspection-gates")
        return self._json(response, expected=(200,), action="GET /inspection-gates")

    # -------------------------------------------------------------- writes
    def report(
        self,
        *,
        unit_operation_id: str,
        attempt_no: int,
        event_type: str,
        occurred_at: datetime,
        reason: str | None = None,
    ) -> dict:
        """Send one WorkEvent with a deterministic, retry-safe event id."""

        self.calls.work_events += 1
        payload = {
            "event_id": (
                f"SIM::{self.run_tag}::{unit_operation_id}::{attempt_no}::{event_type}"
            ),
            "unit_operation_id": unit_operation_id,
            "event_type": event_type,
            "occurred_at": occurred_at.isoformat(),
            "station_code": None,
            "worker_code": self.worker_code,
            "reason": reason,
        }
        response = self.client.post("/work-events", json=payload)
        body = self._json(response, expected=(200, 201), action=f"POST /work-events {event_type}")
        if self.resend_every and self.calls.work_events % self.resend_every == 0:
            repeated = self._json(
                self.client.post("/work-events", json=payload),
                expected=(200,),
                action=f"re-sent POST /work-events {event_type}",
            )
            if not repeated.get("duplicate"):
                raise TerminalError(f"re-sent event was not treated as duplicate: {payload}")
            if (repeated["state"], repeated["attempt_no"]) != (body["state"], body["attempt_no"]):
                raise TerminalError(f"re-sent event changed production state: {payload}")
            self.calls.duplicate_events += 1
        return body

    def estimate_remaining(self, *, unit_operation_id: str, minutes: float) -> dict:
        self.calls.estimates += 1
        response = self.client.patch(
            f"/unit-operations/{unit_operation_id}/expected-remaining",
            json={"expected_remaining_minutes": minutes},
        )
        return self._json(response, expected=(200,), action="PATCH expected-remaining")

    def replan_candidates(self, as_of: datetime) -> dict:
        self.calls.candidate_calculations += 1
        response = self.client.post(
            "/replan-candidates", params={"as_of": as_of.isoformat()}
        )
        return self._json(response, expected=(200,), action="POST /replan-candidates")

    def approve(self, *, parent_plan_id: str, candidate_id: str, as_of: datetime) -> dict:
        self.calls.approvals += 1
        response = self.client.post(
            "/replan-approvals",
            json={
                "parent_plan_id": parent_plan_id,
                "candidate_id": candidate_id,
                "candidate_as_of": as_of.isoformat(),
            },
        )
        return self._json(response, expected=(201,), action="POST /replan-approvals")
