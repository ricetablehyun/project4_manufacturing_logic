"""Transport models for the Production Control API."""

from datetime import datetime

from pydantic import BaseModel, Field, field_validator

from production_control.core.execution_state import WorkEventType


class WorkEventRequest(BaseModel):
    event_id: str = Field(min_length=1)
    unit_operation_id: str = Field(min_length=1)
    event_type: WorkEventType
    occurred_at: datetime
    station_code: str | None = None
    worker_code: str | None = None
    reason: str | None = None

    @field_validator("occurred_at")
    @classmethod
    def require_timezone(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("occurred_at must be timezone-aware")
        return value


class WorkEventResponse(BaseModel):
    event_id: str
    duplicate: bool
    operation_id: str
    lot_id: str
    unit_id: str
    process_code: str
    state: str
    attempt_no: int
    active_minutes: float
    result: str | None


class LotForecastResponse(BaseModel):
    lot_id: str
    forecast_end: datetime
    risk_level: str


class GateForecastResponse(BaseModel):
    gate_id: str
    lot_id: str
    required_after_step_id: str
    gate_type: str
    planned_at: datetime
    forecast_at: datetime
    slack_minutes: float
    risk_level: str


class ProcessForecastResponse(BaseModel):
    lot_id: str
    process_code: str
    forecast_start: datetime
    forecast_end: datetime
    scheduled_operation_count: int


class LiveForecastResponse(BaseModel):
    plan_id: str
    plan_version: int
    as_of: datetime
    readiness: str
    lots: list[LotForecastResponse]
    gates: list[GateForecastResponse]
    processes: list[ProcessForecastResponse]
    missing_gate_ids: list[str]
    waiting_operation_ids: list[str]
