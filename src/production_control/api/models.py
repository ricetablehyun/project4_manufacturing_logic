"""Transport models for the Production Control API."""

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field, field_validator

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


class CurrentPlanTaskResponse(BaseModel):
    lot_id: str
    routing_step_id: str
    process_code: str
    seq_no: int
    target_start: datetime
    target_end: datetime
    target_qty: int
    priority_rank: int


class CurrentPlanResponse(BaseModel):
    plan_id: str
    version: int
    priority_rule: str
    tasks: list[CurrentPlanTaskResponse]


class CandidateKPIResponse(BaseModel):
    late_lot_count: int
    total_tardiness_minutes: float
    overtime_minutes: float
    change_count: int


class ReplanCandidateTaskResponse(BaseModel):
    lot_id: str
    routing_step_id: str
    target_start: datetime
    target_end: datetime
    target_qty: int
    priority_rank: int


class ReplanCandidateResponse(BaseModel):
    candidate_id: str
    rule: str
    kpi: CandidateKPIResponse
    tasks: list[ReplanCandidateTaskResponse]


class ReplanCandidatesResponse(BaseModel):
    parent_plan_id: str
    parent_plan_version: int
    as_of: datetime
    risk_level: str
    action: str
    recommended_candidate_id: str | None
    requires_manager_approval: bool
    candidates: list[ReplanCandidateResponse]


class ReplanApprovalRequest(BaseModel):
    parent_plan_id: str = Field(min_length=1)
    candidate_id: str = Field(min_length=1)
    candidate_as_of: datetime

    @field_validator("candidate_as_of")
    @classmethod
    def require_candidate_timezone(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("candidate_as_of must be timezone-aware")
        return value


class ReplanApprovalResponse(BaseModel):
    plan_id: str
    version: int
    status: str
    parent_plan_id: str
    priority_rule: str
    approved_at: datetime
    selected_candidate_id: str


class LotAdminResponse(BaseModel):
    lot_id: str
    product_id: str
    lot_code: str
    quantity: int
    release_at: datetime
    due_at: datetime
    status: str
    created_at: datetime


class LotUpdateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    release_at: datetime | None = None
    due_at: datetime | None = None
    status: str | None = Field(default=None, min_length=1)

    @field_validator("release_at", "due_at")
    @classmethod
    def require_lot_datetime_timezone(cls, value: datetime | None) -> datetime:
        if value is None:
            raise ValueError("LOT datetime fields may not be null")
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("LOT datetime fields must be timezone-aware")
        return value

    @field_validator("status")
    @classmethod
    def require_lot_status(cls, value: str | None) -> str:
        if value is None:
            raise ValueError("LOT status may not be null")
        return value


class InspectionGateAdminResponse(BaseModel):
    gate_id: str
    lot_id: str
    gate_type: str
    required_after_step_id: str
    planned_at: datetime
    completed_at: datetime | None
    status: str


class InspectionGateUpdateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    planned_at: datetime | None = None
    completed_at: datetime | None = None
    status: str | None = Field(default=None, min_length=1)

    @field_validator("planned_at")
    @classmethod
    def require_planned_at_timezone(cls, value: datetime | None) -> datetime:
        if value is None:
            raise ValueError("planned_at may not be null")
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("planned_at must be timezone-aware")
        return value

    @field_validator("completed_at")
    @classmethod
    def require_completed_at_timezone(cls, value: datetime | None) -> datetime | None:
        if value is not None and (value.tzinfo is None or value.utcoffset() is None):
            raise ValueError("completed_at must be timezone-aware when provided")
        return value

    @field_validator("status")
    @classmethod
    def require_gate_status(cls, value: str | None) -> str:
        if value is None:
            raise ValueError("InspectionGate status may not be null")
        return value
