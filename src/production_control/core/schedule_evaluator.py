"""Derive Gate outcomes and candidate KPIs from a finite schedule.

This layer does not choose a priority rule and does not decide overtime or
change-count policy. It converts a completed Unit-level schedule into the Gate
and candidate metrics already confirmed for V1.
"""

from collections.abc import Iterable
from dataclasses import dataclass
from datetime import datetime

from production_control.core.candidate_evaluator import CandidateKPI
from production_control.core.finite_scheduler import ScheduledOperation
from production_control.core.risk_engine import GateRisk, evaluate_gate_risk


@dataclass(frozen=True, slots=True)
class GateTarget:
    """Scheduling-side Gate target resolved from InspectionGate metadata."""

    gate_id: str
    lot_id: str
    required_step_seq: int
    planned_at: datetime

    def __post_init__(self) -> None:
        if not self.gate_id:
            raise ValueError("gate_id must not be empty")
        if not self.lot_id:
            raise ValueError("lot_id must not be empty")
        if self.required_step_seq <= 0:
            raise ValueError("required_step_seq must be greater than 0")


@dataclass(frozen=True, slots=True)
class GateEvaluation:
    """Forecast and tardiness outcome for one Gate."""

    gate_id: str
    lot_id: str
    required_step_seq: int
    planned_at: datetime
    forecast_at: datetime
    tardiness_minutes: float
    risk: GateRisk


def evaluate_schedule_gates(
    *,
    scheduled_operations: Iterable[ScheduledOperation],
    gate_targets: Iterable[GateTarget],
    warning_threshold_minutes: float,
) -> tuple[GateEvaluation, ...]:
    """Evaluate Gate forecast time from the latest Unit completion at its step."""

    operations = tuple(scheduled_operations)
    evaluations: list[GateEvaluation] = []

    for gate in gate_targets:
        matching = [
            operation
            for operation in operations
            if operation.lot_id == gate.lot_id
            and operation.step_seq == gate.required_step_seq
        ]
        if not matching:
            raise ValueError(
                f"no scheduled operation satisfies Gate {gate.gate_id} "
                f"for LOT {gate.lot_id} at step {gate.required_step_seq}"
            )

        forecast_at = max(operation.end for operation in matching)
        tardiness_minutes = max(
            (forecast_at - gate.planned_at).total_seconds() / 60.0,
            0.0,
        )
        risk = evaluate_gate_risk(
            gate_id=gate.gate_id,
            planned_at=gate.planned_at,
            forecast_at=forecast_at,
            warning_threshold_minutes=warning_threshold_minutes,
        )
        evaluations.append(
            GateEvaluation(
                gate_id=gate.gate_id,
                lot_id=gate.lot_id,
                required_step_seq=gate.required_step_seq,
                planned_at=gate.planned_at,
                forecast_at=forecast_at,
                tardiness_minutes=tardiness_minutes,
                risk=risk,
            )
        )

    return tuple(evaluations)


def build_candidate_kpi(
    *,
    candidate_id: str,
    gate_evaluations: Iterable[GateEvaluation],
    overtime_minutes: float,
    change_count: int,
) -> CandidateKPI:
    """Build D029 candidate metrics from evaluated Gates."""

    evaluations = tuple(gate_evaluations)
    late_lot_ids = {
        evaluation.lot_id
        for evaluation in evaluations
        if evaluation.tardiness_minutes > 0
    }
    total_tardiness = sum(
        evaluation.tardiness_minutes for evaluation in evaluations
    )

    return CandidateKPI(
        candidate_id=candidate_id,
        late_lot_count=len(late_lot_ids),
        total_tardiness_minutes=total_tardiness,
        overtime_minutes=overtime_minutes,
        change_count=change_count,
    )
