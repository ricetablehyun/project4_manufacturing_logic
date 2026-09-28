"""Transport model for operator-facing execution-state reads."""

from datetime import datetime

from pydantic import BaseModel


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
