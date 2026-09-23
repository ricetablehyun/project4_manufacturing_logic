from datetime import datetime
from zoneinfo import ZoneInfo

import pytest

from production_control.core.calendar_engine import WorkSegment
from production_control.core.finite_scheduler import ScheduledOperation
from production_control.core.risk_engine import RiskLevel
from production_control.core.schedule_evaluator import (
    GateTarget,
    build_candidate_kpi,
    evaluate_schedule_gates,
)

SEOUL = ZoneInfo("Asia/Seoul")


def dt(hour: int, minute: int = 0) -> datetime:
    return datetime(2026, 10, 5, hour, minute, tzinfo=SEOUL)


def scheduled(
    operation_id: str,
    lot_id: str,
    unit_id: str,
    step_seq: int,
    start_hour: int,
    start_minute: int,
    end_hour: int,
    end_minute: int,
) -> ScheduledOperation:
    start = dt(start_hour, start_minute)
    end = dt(end_hour, end_minute)
    return ScheduledOperation(
        operation_id=operation_id,
        lot_id=lot_id,
        unit_id=unit_id,
        step_seq=step_seq,
        process_code=f"STEP_{step_seq}",
        start=start,
        end=end,
        segments=(WorkSegment(start=start, end=end),),
    )


def test_gate_forecast_uses_latest_unit_completion_at_required_step() -> None:
    evaluations = evaluate_schedule_gates(
        scheduled_operations=(
            scheduled("U1-S2", "LOT-01", "U1", 2, 9, 0, 9, 30),
            scheduled("U2-S2", "LOT-01", "U2", 2, 9, 0, 9, 45),
        ),
        gate_targets=(GateTarget("G1", "LOT-01", 2, dt(10)),),
        warning_threshold_minutes=30,
    )

    assert evaluations[0].forecast_at == dt(9, 45)
    assert evaluations[0].tardiness_minutes == 0


def test_gate_evaluation_ignores_other_steps() -> None:
    evaluations = evaluate_schedule_gates(
        scheduled_operations=(
            scheduled("U1-S1", "LOT-01", "U1", 1, 9, 0, 11, 0),
            scheduled("U1-S2", "LOT-01", "U1", 2, 9, 0, 9, 30),
        ),
        gate_targets=(GateTarget("G1", "LOT-01", 2, dt(10)),),
        warning_threshold_minutes=30,
    )

    assert evaluations[0].forecast_at == dt(9, 30)


def test_missing_gate_step_is_rejected() -> None:
    with pytest.raises(ValueError):
        evaluate_schedule_gates(
            scheduled_operations=(
                scheduled("U1-S1", "LOT-01", "U1", 1, 9, 0, 9, 30),
            ),
            gate_targets=(GateTarget("G1", "LOT-01", 2, dt(10)),),
            warning_threshold_minutes=30,
        )


def test_late_gate_calculates_tardiness_and_urgent_risk() -> None:
    evaluations = evaluate_schedule_gates(
        scheduled_operations=(
            scheduled("U1-S2", "LOT-01", "U1", 2, 9, 0, 10, 20),
        ),
        gate_targets=(GateTarget("G1", "LOT-01", 2, dt(10)),),
        warning_threshold_minutes=30,
    )

    assert evaluations[0].tardiness_minutes == 20
    assert evaluations[0].risk.risk_level is RiskLevel.URGENT


def test_candidate_counts_one_late_lot_even_with_multiple_late_gates() -> None:
    evaluations = evaluate_schedule_gates(
        scheduled_operations=(
            scheduled("U1-S1", "LOT-01", "U1", 1, 9, 0, 10, 10),
            scheduled("U1-S2", "LOT-01", "U1", 2, 10, 10, 11, 20),
        ),
        gate_targets=(
            GateTarget("G1", "LOT-01", 1, dt(10)),
            GateTarget("G2", "LOT-01", 2, dt(11)),
        ),
        warning_threshold_minutes=30,
    )

    kpi = build_candidate_kpi(
        candidate_id="EDD",
        gate_evaluations=evaluations,
        overtime_minutes=0,
        change_count=0,
    )

    assert kpi.late_lot_count == 1
    assert kpi.total_tardiness_minutes == 30


def test_candidate_counts_distinct_late_lots() -> None:
    evaluations = evaluate_schedule_gates(
        scheduled_operations=(
            scheduled("A-S1", "LOT-A", "U1", 1, 9, 0, 10, 10),
            scheduled("B-S1", "LOT-B", "U1", 1, 9, 0, 10, 20),
        ),
        gate_targets=(
            GateTarget("GA", "LOT-A", 1, dt(10)),
            GateTarget("GB", "LOT-B", 1, dt(10)),
        ),
        warning_threshold_minutes=30,
    )

    kpi = build_candidate_kpi(
        candidate_id="SLACK",
        gate_evaluations=evaluations,
        overtime_minutes=0,
        change_count=0,
    )

    assert kpi.late_lot_count == 2
    assert kpi.total_tardiness_minutes == 30


def test_on_time_candidate_has_zero_tardiness() -> None:
    evaluations = evaluate_schedule_gates(
        scheduled_operations=(
            scheduled("A-S1", "LOT-A", "U1", 1, 9, 0, 9, 50),
        ),
        gate_targets=(GateTarget("GA", "LOT-A", 1, dt(10)),),
        warning_threshold_minutes=30,
    )

    kpi = build_candidate_kpi(
        candidate_id="FCFS",
        gate_evaluations=evaluations,
        overtime_minutes=0,
        change_count=0,
    )

    assert kpi.late_lot_count == 0
    assert kpi.total_tardiness_minutes == 0


def test_overtime_and_change_count_are_passed_into_candidate_kpi() -> None:
    kpi = build_candidate_kpi(
        candidate_id="CR",
        gate_evaluations=(),
        overtime_minutes=120,
        change_count=3,
    )

    assert kpi.overtime_minutes == 120
    assert kpi.change_count == 3
