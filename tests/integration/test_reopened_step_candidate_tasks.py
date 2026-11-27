"""A FINAL_TEST failure can reopen a step the current plan no longer contains.

Found by the repeated experiment: a replan approved after LOT-102 finished
TUNING has no LOT-102 TUNING task; a later FINAL_TEST failure sends a Unit
back to TUNING and candidate generation failed with HTTP 409.
"""

from datetime import timedelta
from pathlib import Path

from production_control.core.calendar_engine import WorkSegment
from production_control.core.finite_scheduler import ScheduledOperation, ScheduleResult
from production_control.persistence.database import (
    create_session_factory,
    create_sqlite_engine,
)
from production_control.persistence.plan_dispatch import load_plan_task_priorities
from production_control.persistence.replan_candidates import _candidate_tasks
from production_control.sim.worlds import F02_START, build_f02_world


def _operation(lot_id: str, unit: str, seq: int, process: str, offset: int) -> ScheduledOperation:
    start = F02_START + timedelta(minutes=offset)
    end = start + timedelta(minutes=25)
    return ScheduledOperation(
        operation_id=f"OP::{lot_id}-{unit}::{process}",
        lot_id=lot_id,
        unit_id=f"{lot_id}-{unit}",
        step_seq=seq,
        process_code=process,
        start=start,
        end=end,
        segments=(WorkSegment(start=start, end=end),),
    )


def test_reopened_step_without_parent_task_gets_a_new_rank(tmp_path: Path) -> None:
    session = create_session_factory(create_sqlite_engine(build_f02_world(tmp_path / "w.db")))()
    parent = tuple(
        priority
        for priority in load_plan_task_priorities(session=session, plan_id="PLAN-F02-BASELINE")
        if not (priority.lot_id == "LOT-102" and priority.process_code == "TUNING")
    )
    schedule = ScheduleResult(
        operations=(
            _operation("LOT-101", "U04", 4, "TUNING", 0),
            _operation("LOT-102", "U03", 4, "TUNING", 25),
            _operation("LOT-102", "U03", 6, "FINAL_TEST", 50),
        ),
        allocations=(),
    )

    tasks, change_count = _candidate_tasks(
        session=session, schedule=schedule, parent_priorities=parent
    )

    by_key = {(task.lot_id, task.routing_step_id): task for task in tasks}
    reopened = by_key[("LOT-102", "STEP-04-TUNING")]
    retest = by_key[("LOT-102", "STEP-06-FINAL-TEST")]
    # Ranks follow the candidate's dispatch order: the reopened TUNING comes
    # before its retest, and one new slot is added after the parent's ranks.
    assert reopened.priority_rank < retest.priority_rank
    assert max(task.priority_rank for task in tasks) == max(p.priority_rank for p in parent) + 1
    assert len({task.priority_rank for task in tasks}) == len(tasks)
    assert change_count >= 0
    session.close()
