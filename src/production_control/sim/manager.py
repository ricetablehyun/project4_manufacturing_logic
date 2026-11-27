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


def _rank_key(row: dict) -> tuple[int, float, float, int]:
    kpi = row["kpi"]
    return (
        int(kpi["late_lot_count"]),
        float(kpi["total_tardiness_minutes"]),
        float(kpi["overtime_minutes"]),
        int(kpi["change_count"]),
    )


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

    by_id = {row["candidate_id"]: row for row in snapshot["candidates"]}
    if policy is ApprovalPolicy.RECOMMENDED:
        chosen_id = snapshot.get("recommended_candidate_id")
    else:
        # The server offers "<RULE>+OT" only when overtime is enabled (D078).
        # The manager keeps the rule and adds overtime only if it ranks better
        # by the same D029 order the system uses.
        chosen_id = policy.value
        overtime = by_id.get(f"{policy.value}+OT")
        base = by_id.get(policy.value)
        if (
            overtime is not None
            and overtime["policy_compliant"]
            and (
                base is None
                or not base["policy_compliant"]
                or _rank_key(overtime) < _rank_key(base)
            )
        ):
            chosen_id = overtime["candidate_id"]
    chosen = by_id.get(chosen_id) if chosen_id is not None else None
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
    unfinished = {
        lot["lot_id"]
        for lot in forecast["lots"]
        if datetime.fromisoformat(lot["forecast_end"]) > at
    }

    def remaining_order(order: list[str] | None) -> list[str]:
        return [lot_id for lot_id in order or [] if lot_id in unfinished]

    if remaining_order(current.get("lot_priority_order")) == remaining_order(
        chosen.get("lot_priority_order")
    ) and not chosen.get("overtime_days"):
        # Approving the order that is already in force for the LOTs still in
        # work would only add a plan version with no change in execution.
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
