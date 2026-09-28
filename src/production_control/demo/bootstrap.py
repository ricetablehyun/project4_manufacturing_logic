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
from production_control.persistence.models import (
    InspectionGateRow,
    LotRow,
    SchedulePlanRow,
    ScheduleTaskRow,
    UnitRow,
)

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


def _demo_date(day: int, hour: int, minute: int = 0) -> datetime:
    return datetime(2026, 10, day, hour, minute, tzinfo=SEOUL)


def apply_demo_fixture_overrides(session: Session) -> None:
    """Apply presentation-only identifiers and a coherent demo inspection timeline.

    Internal primary keys stay unchanged so the approved F02 fixture and its
    regression tests remain stable.  The operator-facing LOT/Unit codes follow
    the confirmed shop-floor convention: LOT codes start at 001 and Unit codes
    continue across LOT boundaries instead of resetting per LOT.

    Shipping-inspection ``planned_at`` means the quality-team-notified
    inspection *start* time.  The three-business-day inspection duration is a
    confirmed demo/domain convention, while the demo due dates below are only
    illustrative dates after inspection completion, not an automatic due-date
    rule.
    """

    lot_specs = (
        (
            "LOT-101",
            "LOT-001",
            _demo_date(8, 17),
            "GATE-LOT-101-SHIPPING-INSPECTION",
            _demo_date(5, 15, 30),
        ),
        (
            "LOT-102",
            "LOT-002",
            _demo_date(9, 17),
            "GATE-LOT-102-SHIPPING-INSPECTION",
            _demo_date(6, 11),
        ),
    )
    for lot_id, lot_code, due_at, gate_id, gate_start in lot_specs:
        lot = session.get(LotRow, lot_id)
        gate = session.get(InspectionGateRow, gate_id)
        if lot is None or gate is None:
            raise RuntimeError(f"demo fixture references missing LOT/Gate: {lot_id}")
        lot.lot_code = lot_code
        lot.due_at = due_at
        gate.planned_at = gate_start

    unit_codes = (
        ("LOT-101-U01", "U001"),
        ("LOT-101-U02", "U002"),
        ("LOT-101-U03", "U003"),
        ("LOT-101-U04", "U004"),
        ("LOT-102-U01", "U005"),
        ("LOT-102-U02", "U006"),
        ("LOT-102-U03", "U007"),
        ("LOT-102-U04", "U008"),
    )
    for unit_id, unit_code in unit_codes:
        unit = session.get(UnitRow, unit_id)
        if unit is None:
            raise RuntimeError(f"demo fixture references missing Unit: {unit_id}")
        unit.unit_code = unit_code

    session.commit()


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
        apply_demo_fixture_overrides(session)
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
