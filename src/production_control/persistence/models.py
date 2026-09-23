"""SQLAlchemy mappings for the confirmed V1 persistence model.

The mappings intentionally stay close to the approved data-model fields.
Core scheduling modules do not import ORM classes.
"""

from datetime import datetime

from sqlalchemy import (
    JSON,
    Boolean,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    String,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    pass


class ProductRow(Base):
    __tablename__ = "product"

    product_id: Mapped[str] = mapped_column(String, primary_key=True)
    product_code: Mapped[str] = mapped_column(String, unique=True, nullable=False)
    name: Mapped[str] = mapped_column(String, nullable=False)
    active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)


class ProcessRow(Base):
    __tablename__ = "process"

    process_id: Mapped[str] = mapped_column(String, primary_key=True)
    process_code: Mapped[str] = mapped_column(String, unique=True, nullable=False)
    name: Mapped[str] = mapped_column(String, nullable=False)
    process_kind: Mapped[str] = mapped_column(String, nullable=False)


class RoutingRow(Base):
    __tablename__ = "routing"

    routing_id: Mapped[str] = mapped_column(String, primary_key=True)
    product_id: Mapped[str] = mapped_column(
        ForeignKey("product.product_id"),
        nullable=False,
    )
    version: Mapped[int] = mapped_column(Integer, nullable=False)
    active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)


class RoutingStepRow(Base):
    __tablename__ = "routing_step"

    routing_step_id: Mapped[str] = mapped_column(String, primary_key=True)
    routing_id: Mapped[str] = mapped_column(
        ForeignKey("routing.routing_id"),
        nullable=False,
    )
    process_id: Mapped[str] = mapped_column(
        ForeignKey("process.process_id"),
        nullable=False,
    )
    seq_no: Mapped[int] = mapped_column(Integer, nullable=False)
    duration_mode: Mapped[str] = mapped_column(String, nullable=False)
    standard_minutes: Mapped[float | None] = mapped_column(Float)
    external_lead_minutes: Mapped[float | None] = mapped_column(Float)
    release_buffer_k: Mapped[int | None] = mapped_column(Integer)


class ResourceRow(Base):
    __tablename__ = "resource"

    resource_id: Mapped[str] = mapped_column(String, primary_key=True)
    resource_code: Mapped[str] = mapped_column(String, unique=True, nullable=False)
    name: Mapped[str] = mapped_column(String, nullable=False)
    resource_type: Mapped[str] = mapped_column(String, nullable=False)
    capacity: Mapped[int] = mapped_column(Integer, nullable=False)
    active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)


class RoutingStepResourceRow(Base):
    __tablename__ = "routing_step_resource"

    routing_step_id: Mapped[str] = mapped_column(
        ForeignKey("routing_step.routing_step_id"),
        primary_key=True,
    )
    resource_id: Mapped[str] = mapped_column(
        ForeignKey("resource.resource_id"),
        primary_key=True,
    )
    required_qty: Mapped[int] = mapped_column(Integer, nullable=False)


class LotRow(Base):
    __tablename__ = "lot"

    lot_id: Mapped[str] = mapped_column(String, primary_key=True)
    product_id: Mapped[str] = mapped_column(
        ForeignKey("product.product_id"),
        nullable=False,
    )
    lot_code: Mapped[str] = mapped_column(String, unique=True, nullable=False)
    quantity: Mapped[int] = mapped_column(Integer, nullable=False)
    release_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    due_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    status: Mapped[str] = mapped_column(String, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class UnitRow(Base):
    __tablename__ = "unit"

    unit_id: Mapped[str] = mapped_column(String, primary_key=True)
    lot_id: Mapped[str] = mapped_column(ForeignKey("lot.lot_id"), nullable=False)
    unit_code: Mapped[str] = mapped_column(String, nullable=False)
    status: Mapped[str] = mapped_column(String, nullable=False)


class UnitOperationRow(Base):
    __tablename__ = "unit_operation"

    unit_operation_id: Mapped[str] = mapped_column(String, primary_key=True)
    unit_id: Mapped[str] = mapped_column(ForeignKey("unit.unit_id"), nullable=False)
    routing_step_id: Mapped[str] = mapped_column(
        ForeignKey("routing_step.routing_step_id"),
        nullable=False,
    )
    state: Mapped[str] = mapped_column(String, nullable=False)
    eligible_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    hold_remaining_minutes: Mapped[float | None] = mapped_column(Float)
    current_attempt_no: Mapped[int] = mapped_column(Integer, nullable=False, default=1)


class WorkAttemptRow(Base):
    __tablename__ = "work_attempt"

    attempt_id: Mapped[str] = mapped_column(String, primary_key=True)
    unit_operation_id: Mapped[str] = mapped_column(
        ForeignKey("unit_operation.unit_operation_id"),
        nullable=False,
    )
    attempt_no: Mapped[int] = mapped_column(Integer, nullable=False)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    ended_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    result: Mapped[str | None] = mapped_column(String)
    active_minutes: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    rework_role: Mapped[str | None] = mapped_column(String)


class WorkEventRow(Base):
    __tablename__ = "work_event"

    event_id: Mapped[str] = mapped_column(String, primary_key=True)
    attempt_id: Mapped[str] = mapped_column(
        ForeignKey("work_attempt.attempt_id"),
        nullable=False,
    )
    event_type: Mapped[str] = mapped_column(String, nullable=False)
    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    station_code: Mapped[str | None] = mapped_column(String)
    worker_code: Mapped[str | None] = mapped_column(String)
    reason: Mapped[str | None] = mapped_column(String)
    received_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class InspectionGateRow(Base):
    __tablename__ = "inspection_gate"

    gate_id: Mapped[str] = mapped_column(String, primary_key=True)
    lot_id: Mapped[str] = mapped_column(ForeignKey("lot.lot_id"), nullable=False)
    gate_type: Mapped[str] = mapped_column(String, nullable=False)
    required_after_step_id: Mapped[str] = mapped_column(
        ForeignKey("routing_step.routing_step_id"),
        nullable=False,
    )
    planned_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    status: Mapped[str] = mapped_column(String, nullable=False)


class WorkCalendarRow(Base):
    __tablename__ = "work_calendar"

    calendar_id: Mapped[str] = mapped_column(String, primary_key=True)
    name: Mapped[str] = mapped_column(String, nullable=False)
    timezone: Mapped[str] = mapped_column(String, nullable=False)
    weekday_start: Mapped[str] = mapped_column(String, nullable=False)
    weekday_end: Mapped[str] = mapped_column(String, nullable=False)
    active_weekdays: Mapped[list[int]] = mapped_column(JSON, nullable=False)


class CalendarExceptionRow(Base):
    __tablename__ = "calendar_exception"

    exception_id: Mapped[str] = mapped_column(String, primary_key=True)
    calendar_id: Mapped[str] = mapped_column(
        ForeignKey("work_calendar.calendar_id"),
        nullable=False,
    )
    resource_id: Mapped[str | None] = mapped_column(ForeignKey("resource.resource_id"))
    start_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    end_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    exception_type: Mapped[str] = mapped_column(String, nullable=False)
    approval_status: Mapped[str] = mapped_column(String, nullable=False)


class SchedulePlanRow(Base):
    __tablename__ = "schedule_plan"

    plan_id: Mapped[str] = mapped_column(String, primary_key=True)
    version: Mapped[int] = mapped_column(Integer, nullable=False)
    plan_kind: Mapped[str] = mapped_column(String, nullable=False)
    priority_rule: Mapped[str] = mapped_column(String, nullable=False)
    status: Mapped[str] = mapped_column(String, nullable=False)
    parent_plan_id: Mapped[str | None] = mapped_column(
        ForeignKey("schedule_plan.plan_id")
    )
    trigger_reason: Mapped[str | None] = mapped_column(String)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    approved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    late_lot_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    total_tardiness_minutes: Mapped[float] = mapped_column(
        Float,
        nullable=False,
        default=0.0,
    )
    overtime_minutes: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    change_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)


class ScheduleTaskRow(Base):
    __tablename__ = "schedule_task"

    schedule_task_id: Mapped[str] = mapped_column(String, primary_key=True)
    plan_id: Mapped[str] = mapped_column(
        ForeignKey("schedule_plan.plan_id"),
        nullable=False,
    )
    lot_id: Mapped[str] = mapped_column(ForeignKey("lot.lot_id"), nullable=False)
    routing_step_id: Mapped[str] = mapped_column(
        ForeignKey("routing_step.routing_step_id"),
        nullable=False,
    )
    target_start: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    target_end: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    target_qty: Mapped[int] = mapped_column(Integer, nullable=False)
    priority_rank: Mapped[int] = mapped_column(Integer, nullable=False)
