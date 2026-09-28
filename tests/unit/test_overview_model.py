from production_control.ui.overview_model import build_overview_view


def _sample_inputs():
    forecast = {
        "plan_id": "PLAN-2",
        "plan_version": 2,
        "as_of": "2026-10-05T10:00:00+09:00",
        "readiness": "READY",
        "lots": [
            {
                "lot_id": "LOT-101",
                "forecast_end": "2026-10-06T11:00:00+09:00",
                "risk_level": "NORMAL",
            },
            {
                "lot_id": "LOT-102",
                "forecast_end": "2026-10-06T17:30:00+09:00",
                "risk_level": "URGENT",
            },
        ],
        "gates": [
            {
                "gate_id": "GATE-102",
                "lot_id": "LOT-102",
                "required_after_step_id": "STEP-06",
                "gate_type": "SHIPPING_INSPECTION",
                "planned_at": "2026-10-06T16:00:00+09:00",
                "forecast_at": "2026-10-06T17:30:00+09:00",
                "slack_minutes": -90.0,
                "risk_level": "URGENT",
            }
        ],
        "processes": [
            {
                "lot_id": "LOT-102",
                "process_code": "TUNING",
                "forecast_start": "2026-10-05T13:00:00+09:00",
                "forecast_end": "2026-10-05T15:00:00+09:00",
                "scheduled_operation_count": 4,
            },
            {
                "lot_id": "LOT-101",
                "process_code": "FINAL_TEST",
                "forecast_start": "2026-10-05T14:00:00+09:00",
                "forecast_end": "2026-10-05T16:00:00+09:00",
                "scheduled_operation_count": 4,
            },
        ],
        "missing_gate_ids": ["GATE-MISSING"],
        "waiting_operation_ids": ["OP-9"],
    }
    lots = [
        {
            "lot_id": "LOT-101",
            "lot_code": "2026-10-A",
            "quantity": 4,
            "due_at": "2026-10-06T12:00:00+09:00",
            "status": "RELEASED",
        },
        {
            "lot_id": "LOT-102",
            "lot_code": "2026-10-B",
            "quantity": 4,
            "due_at": "2026-10-06T16:00:00+09:00",
            "status": "RELEASED",
        },
        {
            "lot_id": "LOT-103",
            "lot_code": "2026-10-C",
            "quantity": 4,
            "due_at": "2026-10-07T12:00:00+09:00",
            "status": "PLANNED",
        },
    ]
    gates = [
        {
            "gate_id": "GATE-102",
            "lot_id": "LOT-102",
            "gate_type": "SHIPPING_INSPECTION",
            "planned_at": "2026-10-06T16:00:00+09:00",
            "completed_at": None,
            "status": "PLANNED",
        }
    ]
    return forecast, lots, gates


def test_overview_metrics_follow_forecast_snapshot():
    forecast, lots, gates = _sample_inputs()

    view = build_overview_view(forecast=forecast, lots=lots, gates=gates)

    assert view.plan_id == "PLAN-2"
    assert view.plan_version == 2
    assert view.readiness == "READY"
    assert view.urgent_lot_count == 1
    assert view.warning_lot_count == 0
    assert view.waiting_operation_count == 1
    assert view.missing_gate_ids == ("GATE-MISSING",)


def test_lot_rows_join_admin_and_forecast_and_sort_risk_first():
    forecast, lots, gates = _sample_inputs()

    view = build_overview_view(forecast=forecast, lots=lots, gates=gates)

    assert [row["lot_id"] for row in view.lot_rows] == ["LOT-102", "LOT-101", "LOT-103"]
    urgent = view.lot_rows[0]
    assert urgent["lot_code"] == "2026-10-B"
    assert urgent["risk_level"] == "URGENT"
    assert urgent["forecast_end"] == "2026-10-06T17:30+09:00"
    assert view.lot_rows[-1]["forecast_end"] == "—"


def test_gate_rows_join_admin_status_with_forecast_risk():
    forecast, lots, gates = _sample_inputs()

    view = build_overview_view(forecast=forecast, lots=lots, gates=gates)

    row = view.gate_rows[0]
    assert row["gate_id"] == "GATE-102"
    assert row["status"] == "PLANNED"
    assert row["slack_minutes"] == -90.0
    assert row["risk_level"] == "URGENT"
    assert row["completed_at"] == "—"


def test_process_rows_are_deterministic_by_lot_and_start():
    forecast, lots, gates = _sample_inputs()

    view = build_overview_view(forecast=forecast, lots=lots, gates=gates)

    assert [row["lot_id"] for row in view.process_rows] == ["LOT-101", "LOT-102"]
    assert view.process_rows[0]["process_code"] == "FINAL_TEST"


def test_forecast_only_lot_is_not_dropped_from_overview():
    forecast, lots, gates = _sample_inputs()
    forecast["lots"].append(
        {
            "lot_id": "LOT-999",
            "forecast_end": "2026-10-08T12:00:00+09:00",
            "risk_level": "WARNING",
        }
    )

    view = build_overview_view(forecast=forecast, lots=lots, gates=gates)

    row = next(row for row in view.lot_rows if row["lot_id"] == "LOT-999")
    assert row["status"] == "UNKNOWN"
    assert row["risk_level"] == "WARNING"
    assert view.warning_lot_count == 1
