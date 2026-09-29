"""Transport models for operator-facing execution-state reads and inputs."""

from datetime import datetime

from pydantic import BaseModel, Field


class UnitOperationResponse(BaseModel):
    operation_id: str
    lot_id: str
    unit_id: str
    unit_code: str
    routing_step_id: str
    seq_no: int
    process_code: str
    state: str
    eligible_at: datetime
    attempt_no: int
    active_minutes: float
    result: str | None
    last_event_at: datetime | None
    expected_remaining_minutes: float | None


class ExpectedRemainingUpdateRequest(BaseModel):
    expected_remaining_minutes: float = Field(gt=0)


class ExpectedRemainingResponse(BaseModel):
    operation_id: str
    expected_remaining_minutes: float
