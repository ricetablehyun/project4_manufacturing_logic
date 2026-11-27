"""Small, explicit worlds for closed-loop tests and demonstrations."""

from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from sqlalchemy import select

from production_control.persistence.database import (
    create_schema,
    create_session_factory,
    create_sqlite_engine,
)
from production_control.persistence.fixture_seed import seed_f02_fixture
from production_control.persistence.materialization import materialize_lot_execution
from production_control.persistence.models import (
    InspectionGateRow,
    SchedulePlanRow,
    ScheduleTaskRow,
)

SEOUL = ZoneInfo("Asia/Seoul")
F02_INTERNAL_STEPS = (
    "STEP-01-TAPING",
    "STEP-03-GENERAL-ASSEMBLY",
    "STEP-04-TUNING",
    "STEP-05-FINISH-ASSEMBLY",
    "STEP-06-FINAL-TEST",
)
F02_START = datetime(2026, 10, 5, 9, 0, tzinfo=SEOUL)


def build_f02_world(
    path: str | Path,
    *,
    baseline_lot_order: tuple[str, ...] = ("LOT-101", "LOT-102"),
    gate_planned_at: dict[str, datetime] | None = None,
) -> Path:
    """F02 regression fixture (2 LOTs x 4 Units) with an explicit baseline order.

    The baseline plan ranks every step of the first LOT before the second LOT.
    Choosing ("LOT-102", "LOT-101") builds a baseline that serves the LOT with
    the later Gate first, which the system should flag and replan.
    """

    database_path = Path(path)
    engine = create_sqlite_engine(database_path)
    create_schema(engine)
    session = create_session_factory(engine)()
    try:
        seed_f02_fixture(session)
        for lot_id in ("LOT-101", "LOT-102"):
            materialize_lot_execution(session=session, lot_id=lot_id)
        for lot_id, planned_at in (gate_planned_at or {}).items():
            gate = session.scalars(
                select(InspectionGateRow).where(InspectionGateRow.lot_id == lot_id)
            ).one()
            gate.planned_at = planned_at
        session.add(
            SchedulePlanRow(
                plan_id="PLAN-F02-BASELINE",
                version=1,
                plan_kind="BASELINE",
                priority_rule="FCFS",
                status="APPROVED",
                parent_plan_id=None,
                trigger_reason=None,
                created_at=F02_START.replace(hour=8),
                approved_at=F02_START.replace(hour=8, minute=30),
                late_lot_count=0,
                total_tardiness_minutes=0,
                overtime_minutes=0,
                change_count=0,
            )
        )
        rank = 1
        for lot_id in baseline_lot_order:
            for step_id in F02_INTERNAL_STEPS:
                session.add(
                    ScheduleTaskRow(
                        schedule_task_id=f"TASK::F02::{lot_id}::{step_id}",
                        plan_id="PLAN-F02-BASELINE",
                        lot_id=lot_id,
                        routing_step_id=step_id,
                        target_start=F02_START,
                        target_end=F02_START.replace(hour=17),
                        target_qty=4,
                        priority_rank=rank,
                    )
                )
                rank += 1
        session.commit()
    finally:
        session.close()
        engine.dispose()
    return database_path
