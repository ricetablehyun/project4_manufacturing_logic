"""Prepare the local demo DB for a quick D072 delay/replan smoke test.

This helper does not change the presentation fixture itself. It advances the
existing U030 RUNNING example into a deterministic Pace-overrun state by
recording a short HOLD -> RESUME pair after the reset snapshot. The operation
returns to RUNNING with more than the 25-minute tuning Pace already consumed,
so Forecast must wait for the worker's expected remaining-time input.

Use only after ``python -m production_control.demo.init_db --reset`` when a
repeatable manual smoke test is desired.
"""

from argparse import ArgumentParser
from datetime import datetime, timedelta
from pathlib import Path

from production_control.core.execution_state import WorkEventInput, WorkEventType
from production_control.demo.bootstrap import (
    DEFAULT_DEMO_DB_PATH,
    DEMO_SNAPSHOT_AT,
    DEMO_SNAPSHOT_RUNNING_OPERATION_ID,
)
from production_control.persistence.database import (
    create_session_factory,
    create_sqlite_engine,
)
from production_control.persistence.execution_service import persist_work_event

_SMOKE_HOLD_EVENT_ID = "DEMO-SMOKE-U030-HOLD"
_SMOKE_RESUME_EVENT_ID = "DEMO-SMOKE-U030-RESUME"


def prepare_delay_smoke(
    path: str | Path = DEFAULT_DEMO_DB_PATH,
) -> datetime:
    """Return U030 to RUNNING after enough active time to exceed tuning Pace."""

    database_path = Path(path)
    if not database_path.exists():
        raise FileNotFoundError(
            f"demo database is not initialized: {database_path}; "
            "run `python -m production_control.demo.init_db --reset` first"
        )

    engine = create_sqlite_engine(database_path)
    session_factory = create_session_factory(engine)
    session = session_factory()

    # Reset snapshot: U030 START 12:50, tuning Pace = 25m. Holding at 13:16
    # closes 26 active minutes, then RESUME at 13:17 leaves the operation
    # RUNNING and immediately actionable under D042/D043/D069.
    hold_at = DEMO_SNAPSHOT_AT + timedelta(minutes=16)
    resume_at = hold_at + timedelta(minutes=1)

    try:
        persist_work_event(
            session=session,
            unit_operation_id=DEMO_SNAPSHOT_RUNNING_OPERATION_ID,
            event=WorkEventInput(
                event_id=_SMOKE_HOLD_EVENT_ID,
                event_type=WorkEventType.HOLD,
                occurred_at=hold_at,
                reason="DELAY_SMOKE_PREP",
            ),
            received_at=hold_at,
            worker_code="DEMO-WORKER",
            expected_hold_minutes=1,
        )
        persist_work_event(
            session=session,
            unit_operation_id=DEMO_SNAPSHOT_RUNNING_OPERATION_ID,
            event=WorkEventInput(
                event_id=_SMOKE_RESUME_EVENT_ID,
                event_type=WorkEventType.RESUME,
                occurred_at=resume_at,
            ),
            received_at=resume_at,
            worker_code="DEMO-WORKER",
        )
    finally:
        session.close()
        engine.dispose()

    return resume_at


def _parse_args() -> ArgumentParser:
    parser = ArgumentParser(description=__doc__)
    parser.add_argument(
        "--db",
        default=str(DEFAULT_DEMO_DB_PATH),
        help="demo SQLite path (default: data/demo.db)",
    )
    return parser


def main() -> None:
    args = _parse_args().parse_args()
    reference_time = prepare_delay_smoke(args.db)
    print(
        "Delay smoke prepared: "
        f"{DEMO_SNAPSHOT_RUNNING_OPERATION_ID} is RUNNING at "
        f"{reference_time.isoformat()} with Pace already exceeded."
    )


if __name__ == "__main__":
    main()
