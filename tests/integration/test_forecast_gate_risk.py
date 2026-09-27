from datetime import datetime
from zoneinfo import ZoneInfo

import pytest
from sqlalchemy import select

from production_control.core.event_scheduler import schedule_operations_event_driven
from production_control.core.finite_scheduler import ScheduleResult
from production_control.core.pace_estimator import estimate_lot_process_work
from production_control.core.pace_scheduler_adapter import ForecastReadiness
from production_control.core.priority_rules import LotPriorityInput, PriorityRule
from production_control.core.risk_engine import RiskLevel
from production_control.persistence.database import (
    create_schema,
    create_session_factory,
    create_sqlite_engine,
)
from production_control.persistence.external_step_barrier import (
    build_full_lot_forecast_inputs,
    save_lot_external_step_state,
)
from production_control.persistence.fixture_seed import seed_f02_fixture
from production_control.persistence.forecast_result import evaluate_persisted_forecast
from production_control.persistence.mappers import (
    load_active_resources,
    load_work_calendar,
)
from production_control.persistence.materialization import materialize_lot_execution
from production_control.persistence.models import (
    InspectionGateRow,
    UnitOperationRow,
    UnitRow,
    WorkAttemptRow,
)

SEOUL = ZoneInfo("Asia/Seoul")
LOT_ID = "LOT-101"
EXTERNAL_STEP_ID = "STEP-02-EXTERNAL-FEED-BONDING"
FINAL_TEST_STEP_ID = "STEP-06-FINAL-TEST"
GATE_ID = "GATE-LOT-101-SHIPPING-INSPECTION"


def dt(day: int, hour: int, minute: int = 0) -> datetime:
    return datetime(2026, 10, day, hour, minute, tzinfo=SEOUL)


def seeded_session_factory():
    engine = create_sqlite_engine()
    create_schema(engine)
    session_factory = create_session_factory(engine)
    session = session_factory()
    seed_f02_fixture(session)
    materialize_lot_execution(session=session, lot_id=LOT_ID)
    session.close()
    return session_factory


def standard_forecasts():
    specs = {
        "TAPING": 10,
        "GENERAL_ASSEMBLY": 10,
        "TUNING": 25,
        "FINISH_ASSEMBLY": 10,
        "FINAL_TEST": 30,
    }
    return {
        process_code: estimate_lot_process_work(
            planned_unit_count=4,
            standard_minutes_per_unit=standard,
            completed_active_minutes=[],
            pace_min_samples=3,
        )
        for process_code, standard in specs.items()
    }


def save_external_expected(session) -> None:
    save_lot_external_step_state(
        session=session,
        lot_id=LOT_ID,
        routing_step_id=EXTERNAL_STEP_ID,
        expected_finish_at=dt(5, 11),
        actual_finish_at=None,
        status="EXPECTED",
        updated_at=dt(5, 9),
    )


def build_schedule(session) -> ScheduleResult:
    bundle = build_full_lot_forecast_inputs(
        session=session,
        lot_id=LOT_ID,
        pace_by_process=standard_forecasts(),
    )
    assert bundle.readiness is ForecastReadiness.READY
    return schedule_operations_event_driven(
        items=bundle.items,
        rule=PriorityRule.EDD,
        static_lot_priorities=(
            LotPriorityInput(
                lot_id=LOT_ID,
                release_at=dt(5, 9),
                deadline=dt(5, 15, 30),
                remaining_work_minutes=340,
                time_until_deadline_minutes=390,
            ),
        ),
        resources=load_active_resources(session),
        calendar=load_work_calendar(session, "CALENDAR-NORMAL"),
        start_time=dt(5, 9),
    )


def test_schedule_aggregates_to_lot_process_and_gate_forecast() -> None:
    session_factory = seeded_session_factory()
    session = session_factory()
    save_external_expected(session)
    schedule = build_schedule(session)

    result = evaluate_persisted_forecast(
        session=session,
        schedule=schedule,
        lot_ids=(LOT_ID,),
        warning_threshold_minutes=10_000,
    )

    assert result.readiness is ForecastReadiness.READY
    assert len(result.process_forecasts) == 5
    assert result.missing_gate_ids == ()
    assert len(result.gate_forecasts) == 1

    final_test = next(
        forecast
        for forecast in result.process_forecasts
        if forecast.process_code == "FINAL_TEST"
    )
    gate = result.gate_forecasts[0]
    assert gate.gate_id == GATE_ID
    assert gate.forecast_at == final_test.forecast_end
    assert gate.risk.slack_minutes > 0
    assert gate.risk.risk_level is RiskLevel.WARNING
    assert result.lot_forecasts[0].risk_level is RiskLevel.WARNING
    session.close()


def test_gate_becomes_urgent_when_forecast_reaches_after_planned_time() -> None:
    session_factory = seeded_session_factory()
    session = session_factory()
    save_external_expected(session)
    gate = session.get(InspectionGateRow, GATE_ID)
    assert gate is not None
    gate.planned_at = dt(5, 12)
    session.commit()
    schedule = build_schedule(session)

    result = evaluate_persisted_forecast(
        session=session,
        schedule=schedule,
        lot_ids=(LOT_ID,),
        warning_threshold_minutes=60,
    )

    gate_forecast = result.gate_forecasts[0]
    assert gate_forecast.risk.slack_minutes <= 0
    assert gate_forecast.risk.risk_level is RiskLevel.URGENT
    assert result.lot_forecasts[0].risk_level is RiskLevel.URGENT
    session.close()


def _mark_final_test_actuals(
    session,
    *,
    failed_unit_id: str | None = None,
) -> datetime:
    operations = session.execute(
        select(UnitOperationRow, UnitRow)
        .join(UnitRow, UnitOperationRow.unit_id == UnitRow.unit_id)
        .where(
            UnitRow.lot_id == LOT_ID,
            UnitOperationRow.routing_step_id == FINAL_TEST_STEP_ID,
        )
        .order_by(UnitRow.unit_id)
    ).all()
    latest = dt(5, 0)
    for index, (operation, unit) in enumerate(operations):
        operation.state = "COMPLETED"
        attempt = session.scalar(
            select(WorkAttemptRow).where(
                WorkAttemptRow.unit_operation_id == operation.unit_operation_id,
                WorkAttemptRow.attempt_no == operation.current_attempt_no,
            )
        )
        assert attempt is not None
        ended_at = dt(5, 13, index * 10)
        attempt.started_at = dt(5, 12, index * 10)
        attempt.ended_at = ended_at
        attempt.result = "FAIL" if unit.unit_id == failed_unit_id else "PASS"
        latest = max(latest, ended_at)
    session.commit()
    return latest


def test_completed_required_step_uses_persisted_actual_completion() -> None:
    session_factory = seeded_session_factory()
    session = session_factory()
    latest = _mark_final_test_actuals(session)

    result = evaluate_persisted_forecast(
        session=session,
        schedule=ScheduleResult(operations=(), allocations=()),
        lot_ids=(LOT_ID,),
        warning_threshold_minutes=60,
    )

    assert result.readiness is ForecastReadiness.READY
    assert result.gate_forecasts[0].forecast_at == latest
    session.close()


def test_failed_final_test_does_not_satisfy_gate_before_retest_exists() -> None:
    session_factory = seeded_session_factory()
    session = session_factory()
    _mark_final_test_actuals(
        session,
        failed_unit_id="LOT-101-U04",
    )

    result = evaluate_persisted_forecast(
        session=session,
        schedule=ScheduleResult(operations=(), allocations=()),
        lot_ids=(LOT_ID,),
        warning_threshold_minutes=60,
    )

    assert result.readiness is ForecastReadiness.WAIT
    assert result.gate_forecasts == ()
    assert result.missing_gate_ids == (GATE_ID,)
    session.close()


def test_external_required_gate_uses_lot_external_barrier() -> None:
    session_factory = seeded_session_factory()
    session = session_factory()
    save_external_expected(session)
    session.add(
        InspectionGateRow(
            gate_id="GATE-LOT-101-EXTERNAL-RETURN",
            lot_id=LOT_ID,
            gate_type="EXTERNAL_RETURN",
            required_after_step_id=EXTERNAL_STEP_ID,
            planned_at=dt(5, 12),
            status="PLANNED",
        )
    )
    session.commit()

    result = evaluate_persisted_forecast(
        session=session,
        schedule=ScheduleResult(operations=(), allocations=()),
        lot_ids=(LOT_ID,),
        warning_threshold_minutes=120,
    )

    external_gate = next(
        gate
        for gate in result.gate_forecasts
        if gate.gate_id == "GATE-LOT-101-EXTERNAL-RETURN"
    )
    assert external_gate.forecast_at == dt(5, 11)
    assert external_gate.risk.risk_level is RiskLevel.WARNING
    assert GATE_ID in result.missing_gate_ids
    session.close()


def test_duplicate_lot_ids_are_rejected() -> None:
    session_factory = seeded_session_factory()
    session = session_factory()

    with pytest.raises(ValueError, match="lot_ids must not contain duplicates"):
        evaluate_persisted_forecast(
            session=session,
            schedule=ScheduleResult(operations=(), allocations=()),
            lot_ids=(LOT_ID, LOT_ID),
            warning_threshold_minutes=60,
        )
    session.close()
