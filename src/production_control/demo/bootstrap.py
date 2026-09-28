"""Explicit bootstrap for the local/demo SQLite database."""

from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from sqlalchemy.orm import Session

from production_control.persistence.database import (
    create_schema,
    create_session_factory,
    create_sqlite_engine,
)
from production_control.persistence.fixture_seed import seed_f02_fixture
from production_control.persistence.materialization import materialize_lot_execution
from production_control.persistence.models import SchedulePlanRow, ScheduleTaskRow

SEOUL = ZoneInfo("Asia/Seoul")
DEFAULT_DEMO_DB_PATH = Path("data/demo.db")
DEMO_PLAN_ID = "PLAN-DEMO-BASELINE-1"
DEMO_LOT_IDS = ("LOT-101", "LOT-102")
DEMO_INTERNAL_STEPS = (
    "STEP-01-TAPING",
    "STEP-03-GENERAL-ASSEMBLY",
    "STEP-04-TUNING",
    "STEP-05-FINISH-ASSEMBLY",
    "STEP-06-FINAL-TEST",
)


def _dt(hour: int, minute: int = 0) -> datetime:
    return datetime(2026, 10, 5, hour, minute, tzinfo=SEOUL)


def seed_demo_baseline_plan(session: Session) -> None:
    """Persist the deterministic baseline plan used by the demo runtime."""

    session.add(
        SchedulePlanRow(
            plan_id=DEMO_PLAN_ID,
            version=1,
            plan_kind="BASELINE",
            priority_rule="EDD",
            status="APPROVED",
            parent_plan_id=None,
            trigger_reason=None,
            created_at=_dt(8),
            approved_at=_dt(8, 30),
            late_lot_count=0,
            total_tardiness_minutes=0,
            overtime_minutes=0,
            change_count=0,
        )
    )

    rank = 1
    for lot_id in DEMO_LOT_IDS:
        for step_id in DEMO_INTERNAL_STEPS:
            session.add(
                ScheduleTaskRow(
                    schedule_task_id=f"TASK::DEMO::{lot_id}::{step_id}",
                    plan_id=DEMO_PLAN_ID,
                    lot_id=lot_id,
                    routing_step_id=step_id,
                    target_start=_dt(9),
                    target_end=_dt(17),
                    target_qty=4,
                    priority_rank=rank,
                )
            )
            rank += 1

    session.commit()


def initialize_demo_database(
    path: str | Path = DEFAULT_DEMO_DB_PATH,
    *,
    reset: bool = False,
) -> Path:
    """Create a deterministic demo DB only when explicitly requested."""

    database_path = Path(path)
    if database_path.exists():
        if not reset:
            raise FileExistsError(
                f"demo database already exists: {database_path}; use --reset to replace it"
            )
        database_path.unlink()

    database_path.parent.mkdir(parents=True, exist_ok=True)
    engine = create_sqlite_engine(database_path)
    create_schema(engine)
    session_factory = create_session_factory(engine)
    session = session_factory()

    try:
        seed_f02_fixture(session)
        for lot_id in DEMO_LOT_IDS:
            materialize_lot_execution(session=session, lot_id=lot_id)
        seed_demo_baseline_plan(session)
    except Exception:
        session.rollback()
        session.close()
        engine.dispose()
        database_path.unlink(missing_ok=True)
        raise
    else:
        session.close()
        engine.dispose()

    return database_path
