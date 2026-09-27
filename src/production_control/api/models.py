"""Transport models for the WorkEvent API."""

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
