"""Virtual production manager: when to review the Forecast and what to approve.

A review reads the Live Forecast. Only when the system itself reports URGENT
Gate risk does the manager request replanning candidates; the policy under test
then decides which candidate, if any, to approve. The manager never edits KPI
or task values: approval goes through the same server-side recomputation as a
human approval.
"""

from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum

from production_control.sim.terminal import ShopFloorTerminal


class ApprovalPolicy(StrEnum):
    """Which candidate the manager approves when the system reports URGENT."""

    KEEP = "KEEP"  # never replan; execute the baseline plan to the end
    FCFS = "FCFS"
    EDD = "EDD"
    SLACK = "SLACK"
    CR = "CR"
    RECOMMENDED = "RECOMMENDED"  # the system's D029 recommendation


@dataclass(frozen=True, slots=True)
class ReviewRecord:
    at: datetime
    trigger: str
    risk: str
    action: str
    candidate_id: str | None = None
    plan_version: int | None = None
    candidate_kpis: tuple[tuple[str, bool, int, float], ...] = ()


def _forecast_risk(forecast: dict) -> str:
    if forecast["readiness"] != "READY":
        return forecast["readiness"]
    levels = {lot["risk_level"] for lot in forecast["lots"]}
    for level in ("URGENT", "WARNING"):
        if level in levels:
            return level
    return "NORMAL"


def review(
    *,
    terminal: ShopFloorTerminal,
    at: datetime,
    trigger: str,
    policy: ApprovalPolicy,
) -> ReviewRecord:
    """Run one manager review at simulated time ``at``."""

    forecast = terminal.forecast(at)
    risk = _forecast_risk(forecast)
    if risk != "URGENT" or policy is ApprovalPolicy.KEEP:
        return ReviewRecord(
            at=at,
            trigger=trigger,
            risk=risk,
            action="NO_REPLAN" if risk != "URGENT" else "KEEP_POLICY",
            plan_version=forecast["plan_version"],
        )

    snapshot = terminal.replan_candidates(at)
    kpis = tuple(
        (
            row["candidate_id"],
            bool(row["policy_compliant"]),
            int(row["kpi"]["late_lot_count"]),
            float(row["kpi"]["total_tardiness_minutes"]),
        )
        for row in snapshot.get("candidates", [])
    )
    if snapshot.get("action") != "GENERATE_CANDIDATES":
        return ReviewRecord(
            at=at,
            trigger=trigger,
            risk=risk,
            action=f"SYSTEM_{snapshot.get('action')}",
            plan_version=forecast["plan_version"],
            candidate_kpis=kpis,
        )

    if policy is ApprovalPolicy.RECOMMENDED:
        chosen_id = snapshot.get("recommended_candidate_id")
    else:
        chosen_id = policy.value
    chosen = next(
        (row for row in snapshot["candidates"] if row["candidate_id"] == chosen_id),
        None,
    )
    if chosen is None or not chosen["policy_compliant"]:
        return ReviewRecord(
            at=at,
            trigger=trigger,
            risk=risk,
            action="NO_APPROVABLE_CANDIDATE",
            candidate_id=chosen_id,
            plan_version=forecast["plan_version"],
            candidate_kpis=kpis,
        )

    current = terminal.current_plan()
    if current.get("lot_priority_order") == chosen.get("lot_priority_order"):
        # Approving the order that is already in force would only add a plan
        # version with no change in execution.
        return ReviewRecord(
            at=at,
            trigger=trigger,
            risk=risk,
            action="ALREADY_IN_FORCE",
            candidate_id=chosen_id,
            plan_version=current["version"],
            candidate_kpis=kpis,
        )

    approval = terminal.approve(
        parent_plan_id=snapshot["parent_plan_id"],
        candidate_id=chosen_id,
        as_of=at,
    )
    return ReviewRecord(
        at=at,
        trigger=trigger,
        risk=risk,
        action="APPROVED",
        candidate_id=chosen_id,
        plan_version=approval["version"],
        candidate_kpis=kpis,
    )
