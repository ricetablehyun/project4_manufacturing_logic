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
    LotExternalStepRow,
    LotRow,
    RoutingStepRow,
    SchedulePlanRow,
    ScheduleTaskRow,
    UnitRow,
)

SEOUL = ZoneInfo("Asia/Seoul")
DEFAULT_DEMO_DB_PATH = Path("data/demo.db")
DEMO_PLAN_ID = "PLAN-DEMO-BASELINE-1"
DEMO_LOT_IDS = ("LOT-101", "LOT-102")
DEMO_QUANTITY = 30
DEMO_INTERNAL_STEPS = (
    "STEP-01-TAPING",
    "STEP-03-GENERAL-ASSEMBLY",
    "STEP-04-TUNING",
    "STEP-05-FINISH-ASSEMBLY",
    "STEP-06-FINAL-TEST",
)
DEMO_EXTERNAL_STEP_ID = "STEP-02-EXTERNAL-FEED-BONDING"


def _demo_dt(month: int, day: int, hour: int, minute: int = 0) -> datetime:
    return datetime(2026, month, day, hour, minute, tzinfo=SEOUL)


def _ensure_demo_units(
    session: Session,
    *,
    lot_id: str,
    display_start: int,
) -> None:
    for lot_unit_index in range(1, DEMO_QUANTITY + 1):
        unit_id = f"{lot_id}-U{lot_unit_index:02d}"
        unit = session.get(UnitRow, unit_id)
        if unit is None:
            unit = UnitRow(
                unit_id=unit_id,
                lot_id=lot_id,
                unit_code="",
                status="WAITING",
            )
            session.add(unit)
        unit.unit_code = f"U{display_start + lot_unit_index - 1:03d}"
        unit.status = "WAITING"


def apply_demo_fixture_overrides(session: Session) -> None:
    """Convert the small F02 seed into a separate presentation demo dataset.

    F02 itself remains a 4-Unit minute-scale regression fixture.  The local
    presentation demo instead uses 30 Units per LOT, globally sequential Unit
    codes, shop-floor remembered LOT-level process windows, K=9 for the first
    downstream release after tuning, and quality-notified shipping-inspection
    start dates.  Unit standard minutes remain the confirmed D035 active-work
    values and are not rewritten into LOT flow-time values.
    """

    lot_specs = (
        (
            "LOT-101",
            "LOT-001",
            _demo_dt(9, 28, 9),
            _demo_dt(10, 29, 17),
            "GATE-LOT-101-SHIPPING-INSPECTION",
            _demo_dt(10, 23, 9),
            _demo_dt(10, 2, 13),
            1,
        ),
        (
            "LOT-102",
            "LOT-002",
            _demo_dt(10, 5, 9),
            _demo_dt(11, 12, 17),
            "GATE-LOT-102-SHIPPING-INSPECTION",
            _demo_dt(11, 6, 9),
            _demo_dt(10, 9, 13),
            31,
        ),
    )

    for (
        lot_id,
        lot_code,
        release_at,
        due_at,
        gate_id,
        gate_start,
        external_finish,
        display_start,
    ) in lot_specs:
        lot = session.get(LotRow, lot_id)
        gate = session.get(InspectionGateRow, gate_id)
        if lot is None or gate is None:
            raise RuntimeError(f"demo fixture references missing LOT/Gate: {lot_id}")

        lot.lot_code = lot_code
        lot.quantity = DEMO_QUANTITY
        lot.release_at = release_at
        lot.due_at = due_at
        lot.status = "ACTIVE"
        lot.created_at = release_at.replace(hour=8)
        gate.planned_at = gate_start
        gate.completed_at = None
        gate.status = "PLANNED"

        _ensure_demo_units(
            session,
            lot_id=lot_id,
            display_start=display_start,
        )

        session.add(
            LotExternalStepRow(
                lot_external_step_id=f"EXT::{lot_id}::{DEMO_EXTERNAL_STEP_ID}",
                lot_id=lot_id,
                routing_step_id=DEMO_EXTERNAL_STEP_ID,
                expected_finish_at=external_finish,
                actual_finish_at=None,
                status="PLANNED",
                updated_at=release_at,
            )
        )

    finish_step = session.get(RoutingStepRow, "STEP-05-FINISH-ASSEMBLY")
    if finish_step is None:
        raise RuntimeError("demo fixture is missing finish-assembly RoutingStep")
    finish_step.release_buffer_k = 9

    session.commit()


def seed_demo_baseline_plan(session: Session) -> None:
    """Persist a LOT x process baseline plan for the presentation demo.

    The task windows are management-level process plans based on the remembered
    shop-floor flow spans recorded in Notion.  They are intentionally separate
    from Unit active standard minutes used by the Forecast engine.
    """

    session.add(
        SchedulePlanRow(
            plan_id=DEMO_PLAN_ID,
            version=1,
            plan_kind="BASELINE",
            priority_rule="EDD",
            status="APPROVED",
            parent_plan_id=None,
            trigger_reason=None,
            created_at=_demo_dt(9, 28, 8),
            approved_at=_demo_dt(9, 28, 8, 30),
            late_lot_count=0,
            total_tardiness_minutes=0,
            overtime_minutes=0,
            change_count=0,
        )
    )

    task_specs = [
        # LOT-001: taping ~1.5d, general assembly ~1.5d, tuning ~10d.
        ("LOT-101", "STEP-01-TAPING", _demo_dt(9, 28, 9), _demo_dt(9, 29, 13)),
        (
            "LOT-101",
            "STEP-03-GENERAL-ASSEMBLY",
            _demo_dt(10, 2, 13),
            _demo_dt(10, 5, 17),
        ),
        ("LOT-101", "STEP-04-TUNING", _demo_dt(10, 6, 9), _demo_dt(10, 19, 17)),
        (
            "LOT-101",
            "STEP-05-FINISH-ASSEMBLY",
            _demo_dt(10, 9, 9),
            _demo_dt(10, 20, 13),
        ),
        (
            "LOT-101",
            "STEP-06-FINAL-TEST",
            _demo_dt(10, 12, 9),
            _demo_dt(10, 22, 17),
        ),
        # LOT-002 enters the same bottleneck station after LOT-001 tuning.
        ("LOT-102", "STEP-01-TAPING", _demo_dt(10, 5, 9), _demo_dt(10, 6, 13)),
        (
            "LOT-102",
            "STEP-03-GENERAL-ASSEMBLY",
            _demo_dt(10, 9, 13),
            _demo_dt(10, 12, 17),
        ),
        ("LOT-102", "STEP-04-TUNING", _demo_dt(10, 20, 9), _demo_dt(11, 2, 17)),
        (
            "LOT-102",
            "STEP-05-FINISH-ASSEMBLY",
            _demo_dt(10, 23, 9),
            _demo_dt(11, 3, 13),
        ),
        (
            "LOT-102",
            "STEP-06-FINAL-TEST",
            _demo_dt(10, 26, 9),
            _demo_dt(11, 5, 17),
        ),
    ]
    task_specs.sort(key=lambda item: (item[2], item[0], item[1]))

    for rank, (lot_id, step_id, target_start, target_end) in enumerate(
        task_specs,
        start=1,
    ):
        session.add(
            ScheduleTaskRow(
                schedule_task_id=f"TASK::DEMO::{lot_id}::{step_id}",
                plan_id=DEMO_PLAN_ID,
                lot_id=lot_id,
                routing_step_id=step_id,
                target_start=target_start,
                target_end=target_end,
                target_qty=DEMO_QUANTITY,
                priority_rank=rank,
            )
        )

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
