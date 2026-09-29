from production_control.ui.replan_view_model import (
    build_plan_change_rows,
    build_priority_change_rows,
    rank_replan_candidates,
    summarize_replan_status,
)


def test_replan_status_wait_does_not_infer_gate_risk() -> None:
    summary = summarize_replan_status(
        readiness="WAIT",
        gate_rows=(
            {
                "gate_id": "G1",
                "lot_id": "LOT-1",
                "gate_type": "SHIPPING_INSPECTION",
                "risk_level": "URGENT",
                "slack_minutes": -30,
            },
        ),
    )

    assert summary.readiness == "WAIT"
    assert summary.risk_level == "UNKNOWN"
    assert summary.lot_id is None
    assert summary.slack_minutes is None


def test_replan_status_picks_most_severe_gate_then_tightest_slack() -> None:
    summary = summarize_replan_status(
        readiness="READY",
        gate_rows=(
            {
                "gate_id": "G-NORMAL",
                "lot_id": "LOT-1",
                "gate_type": "SHIPPING_INSPECTION",
                "risk_level": "NORMAL",
                "slack_minutes": 300,
            },
            {
                "gate_id": "G-URGENT-1",
                "lot_id": "LOT-2",
                "gate_type": "SHIPPING_INSPECTION",
                "risk_level": "URGENT",
                "slack_minutes": -20,
            },
            {
                "gate_id": "G-URGENT-2",
                "lot_id": "LOT-3",
                "gate_type": "SHIPPING_INSPECTION",
                "risk_level": "URGENT",
                "slack_minutes": -50,
            },
        ),
    )

    assert summary.risk_level == "URGENT"
    assert summary.lot_id == "LOT-3"
    assert summary.slack_minutes == -50


def test_rank_replan_candidates_uses_d029_best_first_and_policy_last() -> None:
    candidates = (
        {
            "candidate_id": "FCFS",
            "policy_compliant": True,
            "kpi": {
                "late_lot_count": 1,
                "total_tardiness_minutes": 120,
                "overtime_minutes": 0,
                "change_count": 1,
            },
        },
        {
            "candidate_id": "EDD",
            "policy_compliant": True,
            "kpi": {
                "late_lot_count": 0,
                "total_tardiness_minutes": 0,
                "overtime_minutes": 0,
                "change_count": 4,
            },
        },
        {
            "candidate_id": "CR",
            "policy_compliant": False,
            "kpi": {
                "late_lot_count": 0,
                "total_tardiness_minutes": 0,
                "overtime_minutes": 0,
                "change_count": 0,
            },
        },
    )

    ranked = rank_replan_candidates(candidates)

    assert [row["candidate_id"] for row in ranked] == ["EDD", "FCFS", "CR"]
    assert [row["rank"] for row in ranked] == [1, 2, None]
    assert ranked[-1]["policy_compliant"] is False


def test_rank_replan_candidates_preserves_exact_ties_without_false_preference() -> None:
    tied_kpi = {
        "late_lot_count": 1,
        "total_tardiness_minutes": 60,
        "overtime_minutes": 0,
        "change_count": 2,
    }
    ranked = rank_replan_candidates(
        (
            {
                "candidate_id": "FCFS",
                "policy_compliant": True,
                "kpi": tied_kpi,
            },
            {
                "candidate_id": "EDD",
                "policy_compliant": True,
                "kpi": dict(tied_kpi),
            },
        )
    )

    assert [row["rank"] for row in ranked] == [1, 1]
    assert all(row["tied"] is True for row in ranked)


def test_plan_change_rows_include_time_window_change_even_when_priority_is_same() -> None:
    current = (
        {
            "lot_id": "LOT-101",
            "routing_step_id": "STEP-TUNING",
            "process_code": "TUNING",
            "target_start": "2026-10-22T13:00:00+09:00",
            "target_end": "2026-10-22T14:00:00+09:00",
            "priority_rank": 3,
        },
    )
    candidate = (
        {
            "lot_id": "LOT-101",
            "routing_step_id": "STEP-TUNING",
            "target_start": "2026-10-22T13:30:00+09:00",
            "target_end": "2026-10-22T14:30:00+09:00",
            "priority_rank": 3,
        },
    )

    rows = build_plan_change_rows(
        current_tasks=current,
        candidate_tasks=candidate,
        lot_code_by_id={"LOT-101": "LOT-001"},
    )

    assert len(rows) == 1
    assert rows[0]["lot_code"] == "LOT-001"
    assert rows[0]["start_shift_minutes"] == 30
    assert rows[0]["end_shift_minutes"] == 30
    assert rows[0]["priority_movement"] == "유지"


def test_priority_change_rows_show_only_changed_lot_process_ranks() -> None:
    current = (
        {
            "lot_id": "LOT-101",
            "routing_step_id": "STEP-TUNING",
            "process_code": "TUNING",
            "priority_rank": 2,
        },
        {
            "lot_id": "LOT-102",
            "routing_step_id": "STEP-TUNING",
            "process_code": "TUNING",
            "priority_rank": 1,
        },
        {
            "lot_id": "LOT-101",
            "routing_step_id": "STEP-TEST",
            "process_code": "FINAL_TEST",
            "priority_rank": 3,
        },
    )
    candidate = (
        {
            "lot_id": "LOT-101",
            "routing_step_id": "STEP-TUNING",
            "priority_rank": 1,
        },
        {
            "lot_id": "LOT-102",
            "routing_step_id": "STEP-TUNING",
            "priority_rank": 2,
        },
        {
            "lot_id": "LOT-101",
            "routing_step_id": "STEP-TEST",
            "priority_rank": 3,
        },
    )

    rows = build_priority_change_rows(
        current_tasks=current,
        candidate_tasks=candidate,
        lot_code_by_id={"LOT-101": "LOT-001", "LOT-102": "LOT-002"},
    )

    assert rows == (
        {
            "lot_id": "LOT-101",
            "lot_code": "LOT-001",
            "routing_step_id": "STEP-TUNING",
            "process_code": "TUNING",
            "current_rank": 2,
            "candidate_rank": 1,
            "movement": "앞당김",
        },
        {
            "lot_id": "LOT-102",
            "lot_code": "LOT-002",
            "routing_step_id": "STEP-TUNING",
            "process_code": "TUNING",
            "current_rank": 1,
            "candidate_rank": 2,
            "movement": "뒤로",
        },
    )


def test_priority_change_rows_ignore_unknown_candidate_task() -> None:
    rows = build_priority_change_rows(
        current_tasks=(),
        candidate_tasks=(
            {
                "lot_id": "LOT-X",
                "routing_step_id": "STEP-X",
                "priority_rank": 1,
            },
        ),
        lot_code_by_id={},
    )

    assert rows == ()
