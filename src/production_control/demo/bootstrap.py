"""Explicit bootstrap for the local/demo SQLite database."""

from datetime import datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

from sqlalchemy.orm import Session

from production_control.core.execution_state import WorkEventInput, WorkEventType
from production_control.persistence.database import (
    create_schema,
    create_session_factory,
    create_sqlite_engine,
)
from production_control.persistence.execution_service import persist_work_event
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


DEMO_SNAPSHOT_AT = _demo_dt(10, 14, 13)
DEMO_SNAPSHOT_RUNNING_OPERATION_ID = "OP::LOT-101-U18::STEP-04-TUNING"


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

    F02 itself remains a 4-Unit minute-scale regression fixture. The local
    presentation demo instead uses 30 Units per LOT, globally sequential Unit
    codes, shop-floor remembered LOT-level process windows, K=9 for the first
    downstream release after tuning, and quality-notified shipping-inspection
    start dates. Unit standard minutes remain the confirmed D035 active-work
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


def _operation_id(lot_id: str, unit_index: int, step_id: str) -> str:
    return f"OP::{lot_id}-U{unit_index:02d}::{step_id}"


def _record_demo_event(
    session: Session,
    *,
    lot_id: str,
    unit_index: int,
    step_id: str,
    event_type: WorkEventType,
    occurred_at: datetime,
    reason: str | None = None,
) -> None:
    event_id = (
        f"DEMO::{lot_id}::U{unit_index:02d}::{step_id}::{event_type.value}"
    )
    persist_work_event(
        session=session,
        unit_operation_id=_operation_id(lot_id, unit_index, step_id),
        event=WorkEventInput(
            event_id=event_id,
            event_type=event_type,
            occurred_at=occurred_at,
            reason=reason,
        ),
        received_at=occurred_at,
        worker_code="DEMO-WORKER",
    )


def _complete_unit_operation(
    session: Session,
    *,
    lot_id: str,
    unit_index: int,
    step_id: str,
    started_at: datetime,
    duration_minutes: int,
    terminal_event: WorkEventType = WorkEventType.COMPLETE,
) -> None:
    _record_demo_event(
        session,
        lot_id=lot_id,
        unit_index=unit_index,
        step_id=step_id,
        event_type=WorkEventType.START,
        occurred_at=started_at,
    )
    _record_demo_event(
        session,
        lot_id=lot_id,
        unit_index=unit_index,
        step_id=step_id,
        event_type=terminal_event,
        occurred_at=started_at + timedelta(minutes=duration_minutes),
    )


def _complete_unit_range(
    session: Session,
    *,
    lot_id: str,
    unit_indices: range,
    step_id: str,
    started_at: datetime,
    duration_minutes: int,
    parallelism: int,
    terminal_event: WorkEventType = WorkEventType.COMPLETE,
) -> None:
    for offset, unit_index in enumerate(unit_indices):
        slot = offset // parallelism
        _complete_unit_operation(
            session,
            lot_id=lot_id,
            unit_index=unit_index,
            step_id=step_id,
            started_at=started_at + timedelta(minutes=slot * duration_minutes),
            duration_minutes=duration_minutes,
            terminal_event=terminal_event,
        )


def seed_demo_execution_snapshot(session: Session) -> None:
    """Seed the presentation DB at a deterministic mid-production snapshot.

    The snapshot is intentionally not the beginning of production. LOT-001 has
    progressed into tuning, downstream transfer has already begun after K=9,
    and LOT-002 is waiting for the shared tuning bottleneck. The presenter can
    therefore demonstrate one shop-floor exception without manually creating
    several days of history first.
    """

    for lot_id in DEMO_LOT_IDS:
        external = session.get(
            LotExternalStepRow,
            f"EXT::{lot_id}::{DEMO_EXTERNAL_STEP_ID}",
        )
        if external is None:
            raise RuntimeError(f"demo external step is missing: {lot_id}")
        external.actual_finish_at = external.expected_finish_at
        external.status = "COMPLETED"
        external.updated_at = external.expected_finish_at
    session.commit()

    # LOT-001: prior internal work completed before the current tuning stage.
    _complete_unit_range(
        session,
        lot_id="LOT-101",
        unit_indices=range(1, 31),
        step_id="STEP-01-TAPING",
        started_at=_demo_dt(9, 28, 9),
        duration_minutes=10,
        parallelism=2,
    )
    _complete_unit_range(
        session,
        lot_id="LOT-101",
        unit_indices=range(1, 31),
        step_id="STEP-03-GENERAL-ASSEMBLY",
        started_at=_demo_dt(10, 5, 9),
        duration_minutes=10,
        parallelism=2,
    )

    tuning_starts = (
        (1, _demo_dt(10, 6, 9)),
        (2, _demo_dt(10, 6, 11)),
        (3, _demo_dt(10, 6, 14)),
        (4, _demo_dt(10, 7, 9)),
        (5, _demo_dt(10, 7, 11)),
        (6, _demo_dt(10, 7, 14)),
        (7, _demo_dt(10, 8, 9)),
        (8, _demo_dt(10, 8, 11)),
        (9, _demo_dt(10, 8, 14)),
        (10, _demo_dt(10, 9, 9)),
        (11, _demo_dt(10, 9, 13)),
        (12, _demo_dt(10, 12, 9)),
        (13, _demo_dt(10, 12, 13)),
        (14, _demo_dt(10, 13, 9)),
        (15, _demo_dt(10, 13, 11)),
        (16, _demo_dt(10, 13, 14)),
        (17, _demo_dt(10, 14, 9)),
    )
    for unit_index, started_at in tuning_starts:
        _complete_unit_operation(
            session,
            lot_id="LOT-101",
            unit_index=unit_index,
            step_id="STEP-04-TUNING",
            started_at=started_at,
            duration_minutes=25,
        )

    # K=9 has already released the downstream flow for the first transfer set.
    _complete_unit_range(
        session,
        lot_id="LOT-101",
        unit_indices=range(1, 9),
        step_id="STEP-05-FINISH-ASSEMBLY",
        started_at=_demo_dt(10, 9, 14),
        duration_minutes=10,
        parallelism=2,
    )
    _complete_unit_range(
        session,
        lot_id="LOT-101",
        unit_indices=range(1, 5),
        step_id="STEP-06-FINAL-TEST",
        started_at=_demo_dt(10, 14, 9),
        duration_minutes=30,
        parallelism=1,
        terminal_event=WorkEventType.PASS,
    )

    # U018 is the one live tuning operation used for the HOLD demonstration.
    _record_demo_event(
        session,
        lot_id="LOT-101",
        unit_index=18,
        step_id="STEP-04-TUNING",
        event_type=WorkEventType.START,
        occurred_at=_demo_dt(10, 14, 12, 50),
    )

    # One downstream completion fixes the snapshot reference at exactly 13:00.
    _complete_unit_operation(
        session,
        lot_id="LOT-101",
        unit_index=9,
        step_id="STEP-05-FINISH-ASSEMBLY",
        started_at=_demo_dt(10, 14, 12, 50),
        duration_minutes=10,
    )

    # LOT-002 has finished its upstream work and waits for the same tuning station.
    _complete_unit_range(
        session,
        lot_id="LOT-102",
        unit_indices=range(1, 31),
        step_id="STEP-01-TAPING",
        started_at=_demo_dt(10, 5, 9),
        duration_minutes=10,
        parallelism=2,
    )
    _complete_unit_range(
        session,
        lot_id="LOT-102",
        unit_indices=range(1, 31),
        step_id="STEP-03-GENERAL-ASSEMBLY",
        started_at=_demo_dt(10, 12, 9),
        duration_minutes=10,
        parallelism=2,
    )


def seed_demo_baseline_plan(session: Session) -> None:
    """Persist a LOT x process baseline plan for the presentation demo.

    The task windows are management-level process plans based on the remembered
    shop-floor flow spans recorded in Notion. They are intentionally separate
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
        seed_demo_execution_snapshot(session)
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
