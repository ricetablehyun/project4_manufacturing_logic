"""Deterministic F02 persistence seed from the approved V1 fixture.

The seed deliberately stores only values that the fixture defines.
The F02 external process has no fixed lead-time number, so its
external_lead_minutes remains NULL rather than inventing one.
"""

from datetime import datetime
from zoneinfo import ZoneInfo

from sqlalchemy.orm import Session

from production_control.persistence.models import (
    InspectionGateRow,
    LotRow,
    ProcessRow,
    ProductRow,
    ResourceRow,
    RoutingRow,
    RoutingStepResourceRow,
    RoutingStepRow,
    UnitRow,
    WorkCalendarRow,
)

SEOUL = ZoneInfo("Asia/Seoul")


def _dt(year: int, month: int, day: int, hour: int, minute: int = 0) -> datetime:
    return datetime(year, month, day, hour, minute, tzinfo=SEOUL)


def seed_f02_fixture(session: Session) -> None:
    """Persist the confirmed F02 master/LOT/Gate fixture."""

    product = ProductRow(
        product_id="PRODUCT-RF-MOCK-A",
        product_code="RF-MOCK-A",
        name="RF Mock A",
        active=True,
    )
    processes = (
        ProcessRow(
            process_id="PROCESS-TAPING",
            process_code="TAPING",
            name="Taping",
            process_kind="INTERNAL",
        ),
        ProcessRow(
            process_id="PROCESS-EXTERNAL-FEED-BONDING",
            process_code="EXTERNAL_FEED_BONDING",
            name="External Feed Bonding",
            process_kind="EXTERNAL",
        ),
        ProcessRow(
            process_id="PROCESS-GENERAL-ASSEMBLY",
            process_code="GENERAL_ASSEMBLY",
            name="General Assembly",
            process_kind="INTERNAL",
        ),
        ProcessRow(
            process_id="PROCESS-TUNING",
            process_code="TUNING",
            name="Tuning",
            process_kind="INTERNAL",
        ),
        ProcessRow(
            process_id="PROCESS-FINISH-ASSEMBLY",
            process_code="FINISH_ASSEMBLY",
            name="Finish Assembly",
            process_kind="INTERNAL",
        ),
        ProcessRow(
            process_id="PROCESS-FINAL-TEST",
            process_code="FINAL_TEST",
            name="Final Test",
            process_kind="INTERNAL",
        ),
    )
    resources = (
        ResourceRow(
            resource_id="RESOURCE-WORKER-POOL",
            resource_code="WORKER_POOL",
            name="Worker Pool",
            resource_type="HUMAN_POOL",
            capacity=2,
            active=True,
        ),
        ResourceRow(
            resource_id="RESOURCE-TUNING-STATION",
            resource_code="TUNING_STATION",
            name="Tuning Station",
            resource_type="MACHINE",
            capacity=1,
            active=True,
        ),
        ResourceRow(
            resource_id="RESOURCE-TEST-STATION",
            resource_code="TEST_STATION",
            name="Test Station",
            resource_type="MACHINE",
            capacity=1,
            active=True,
        ),
    )
    calendar = WorkCalendarRow(
        calendar_id="CALENDAR-NORMAL",
        name="Normal Weekday Calendar",
        timezone="Asia/Seoul",
        weekday_start="09:00",
        weekday_end="17:00",
        active_weekdays=[0, 1, 2, 3, 4],
    )

    session.add(product)
    session.add_all(processes)
    session.add_all(resources)
    session.add(calendar)
    session.flush()

    routing = RoutingRow(
        routing_id="ROUTING-RF-MOCK-A-V1",
        product_id=product.product_id,
        version=1,
        active=True,
    )
    session.add(routing)
    session.flush()

    steps = (
        RoutingStepRow(
            routing_step_id="STEP-01-TAPING",
            routing_id=routing.routing_id,
            process_id="PROCESS-TAPING",
            seq_no=1,
            duration_mode="UNIT_TIME",
            standard_minutes=10,
        ),
        RoutingStepRow(
            routing_step_id="STEP-02-EXTERNAL-FEED-BONDING",
            routing_id=routing.routing_id,
            process_id="PROCESS-EXTERNAL-FEED-BONDING",
            seq_no=2,
            duration_mode="LOT_LEAD_TIME",
            external_lead_minutes=None,
        ),
        RoutingStepRow(
            routing_step_id="STEP-03-GENERAL-ASSEMBLY",
            routing_id=routing.routing_id,
            process_id="PROCESS-GENERAL-ASSEMBLY",
            seq_no=3,
            duration_mode="UNIT_TIME",
            standard_minutes=10,
        ),
        RoutingStepRow(
            routing_step_id="STEP-04-TUNING",
            routing_id=routing.routing_id,
            process_id="PROCESS-TUNING",
            seq_no=4,
            duration_mode="UNIT_TIME",
            standard_minutes=25,
        ),
        RoutingStepRow(
            routing_step_id="STEP-05-FINISH-ASSEMBLY",
            routing_id=routing.routing_id,
            process_id="PROCESS-FINISH-ASSEMBLY",
            seq_no=5,
            duration_mode="UNIT_TIME",
            standard_minutes=10,
            release_buffer_k=2,
        ),
        RoutingStepRow(
            routing_step_id="STEP-06-FINAL-TEST",
            routing_id=routing.routing_id,
            process_id="PROCESS-FINAL-TEST",
            seq_no=6,
            duration_mode="UNIT_TIME",
            standard_minutes=30,
        ),
    )
    session.add_all(steps)
    session.flush()

    session.add_all(
        (
            RoutingStepResourceRow(
                routing_step_id="STEP-01-TAPING",
                resource_id="RESOURCE-WORKER-POOL",
                required_qty=1,
            ),
            RoutingStepResourceRow(
                routing_step_id="STEP-03-GENERAL-ASSEMBLY",
                resource_id="RESOURCE-WORKER-POOL",
                required_qty=1,
            ),
            RoutingStepResourceRow(
                routing_step_id="STEP-04-TUNING",
                resource_id="RESOURCE-WORKER-POOL",
                required_qty=1,
            ),
            RoutingStepResourceRow(
                routing_step_id="STEP-04-TUNING",
                resource_id="RESOURCE-TUNING-STATION",
                required_qty=1,
            ),
            RoutingStepResourceRow(
                routing_step_id="STEP-05-FINISH-ASSEMBLY",
                resource_id="RESOURCE-WORKER-POOL",
                required_qty=1,
            ),
            RoutingStepResourceRow(
                routing_step_id="STEP-06-FINAL-TEST",
                resource_id="RESOURCE-WORKER-POOL",
                required_qty=1,
            ),
            RoutingStepResourceRow(
                routing_step_id="STEP-06-FINAL-TEST",
                resource_id="RESOURCE-TEST-STATION",
                required_qty=1,
            ),
        )
    )

    lot_101 = LotRow(
        lot_id="LOT-101",
        product_id=product.product_id,
        lot_code="LOT-101",
        quantity=4,
        release_at=_dt(2026, 10, 5, 9),
        due_at=_dt(2026, 10, 6, 12),
        status="ACTIVE",
        created_at=_dt(2026, 10, 5, 8),
    )
    lot_102 = LotRow(
        lot_id="LOT-102",
        product_id=product.product_id,
        lot_code="LOT-102",
        quantity=4,
        release_at=_dt(2026, 10, 5, 9),
        due_at=_dt(2026, 10, 6, 16),
        status="ACTIVE",
        created_at=_dt(2026, 10, 5, 8),
    )
    session.add_all((lot_101, lot_102))
    session.flush()

    session.add_all(
        tuple(
            UnitRow(
                unit_id=f"{lot_id}-{unit_code}",
                lot_id=lot_id,
                unit_code=unit_code,
                status="WAITING",
            )
            for lot_id in ("LOT-101", "LOT-102")
            for unit_code in ("U01", "U02", "U03", "U04")
        )
    )
    session.add_all(
        (
            InspectionGateRow(
                gate_id="GATE-LOT-101-SHIPPING-INSPECTION",
                lot_id="LOT-101",
                gate_type="SHIPPING_INSPECTION",
                required_after_step_id="STEP-06-FINAL-TEST",
                planned_at=_dt(2026, 10, 5, 15, 30),
                status="PLANNED",
            ),
            InspectionGateRow(
                gate_id="GATE-LOT-102-SHIPPING-INSPECTION",
                lot_id="LOT-102",
                gate_type="SHIPPING_INSPECTION",
                required_after_step_id="STEP-06-FINAL-TEST",
                planned_at=_dt(2026, 10, 6, 11),
                status="PLANNED",
            ),
        )
    )
    session.commit()
