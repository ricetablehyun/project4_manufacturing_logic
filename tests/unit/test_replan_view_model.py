from production_control.ui.replan_view_model import (
    build_priority_change_rows,
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
