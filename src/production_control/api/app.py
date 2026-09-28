"""Thin FastAPI boundary over persisted production-control services."""

from collections.abc import Iterator
from datetime import UTC, datetime
from typing import Annotated

from fastapi import Depends, FastAPI, HTTPException, Response, status
from sqlalchemy.orm import Session, sessionmaker

from production_control.api.models import (
    CandidateKPIResponse,
    GateForecastResponse,
    LiveForecastResponse,
    LotForecastResponse,
    ProcessForecastResponse,
    ReplanCandidateResponse,
    ReplanCandidatesResponse,
    ReplanCandidateTaskResponse,
    WorkEventRequest,
    WorkEventResponse,
)
from production_control.core.execution_state import WorkEventInput
from production_control.persistence.execution_service import persist_work_event
from production_control.persistence.live_forecast import (
    LiveForecastConfig,
    build_live_forecast,
)
from production_control.persistence.replan_candidates import build_replan_candidates


def create_app(
    *,
    session_factory: sessionmaker[Session],
    forecast_config: LiveForecastConfig | None = None,
) -> FastAPI:
    """Create the API without inventing deployment-time database configuration."""

    app = FastAPI(title="Production Control API")

    def get_session() -> Iterator[Session]:
        session = session_factory()
        try:
            yield session
        finally:
            session.close()

    def require_forecast_config() -> LiveForecastConfig:
        if forecast_config is None:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="Live Forecast configuration is not available",
            )
        return forecast_config

    def resolve_reference_time(as_of: datetime | None) -> datetime:
        reference_time = as_of or datetime.now(UTC)
        if reference_time.tzinfo is None or reference_time.utcoffset() is None:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                detail="as_of must be timezone-aware",
            )
        return reference_time

    @app.post(
        "/work-events",
        response_model=WorkEventResponse,
        status_code=status.HTTP_201_CREATED,
    )
    def create_work_event(
        payload: WorkEventRequest,
        response: Response,
        session: Annotated[Session, Depends(get_session)],
    ) -> WorkEventResponse:
        event = WorkEventInput(
            event_id=payload.event_id,
            event_type=payload.event_type,
            occurred_at=payload.occurred_at,
            reason=payload.reason,
        )

        try:
            result = persist_work_event(
                session=session,
                unit_operation_id=payload.unit_operation_id,
                event=event,
                received_at=datetime.now(UTC),
                station_code=payload.station_code,
                worker_code=payload.worker_code,
            )
        except ValueError as exc:
            session.rollback()
            detail = str(exc)
            http_status = (
                status.HTTP_404_NOT_FOUND
                if detail.startswith("unknown unit_operation_id:")
                else status.HTTP_409_CONFLICT
            )
            raise HTTPException(status_code=http_status, detail=detail) from exc

        if result.duplicate:
            response.status_code = status.HTTP_200_OK

        snapshot = result.snapshot
        return WorkEventResponse(
            event_id=payload.event_id,
            duplicate=result.duplicate,
            operation_id=snapshot.operation_id,
            lot_id=snapshot.lot_id,
            unit_id=snapshot.unit_id,
            process_code=snapshot.process_code,
            state=snapshot.state.value,
            attempt_no=snapshot.attempt_no,
            active_minutes=snapshot.active_minutes,
            result=snapshot.result.value if snapshot.result is not None else None,
        )

    @app.get("/forecast", response_model=LiveForecastResponse)
    def get_forecast(
        session: Annotated[Session, Depends(get_session)],
        as_of: datetime | None = None,
    ) -> LiveForecastResponse:
        config = require_forecast_config()
        reference_time = resolve_reference_time(as_of)

        try:
            snapshot = build_live_forecast(
                session=session,
                as_of=reference_time,
                config=config,
            )
        except ValueError as exc:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=str(exc),
            ) from exc

        result = snapshot.result
        if result is None:
            return LiveForecastResponse(
                plan_id=snapshot.plan_id,
                plan_version=snapshot.plan_version,
                as_of=snapshot.as_of,
                readiness=snapshot.readiness.value,
                lots=[],
                gates=[],
                processes=[],
                missing_gate_ids=[],
                waiting_operation_ids=list(snapshot.waiting_operation_ids),
            )

        return LiveForecastResponse(
            plan_id=snapshot.plan_id,
            plan_version=snapshot.plan_version,
            as_of=snapshot.as_of,
            readiness=snapshot.readiness.value,
            lots=[
                LotForecastResponse(
                    lot_id=forecast.lot_id,
                    forecast_end=forecast.forecast_end,
                    risk_level=forecast.risk_level.name,
                )
                for forecast in result.lot_forecasts
            ],
            gates=[
                GateForecastResponse(
                    gate_id=forecast.gate_id,
                    lot_id=forecast.lot_id,
                    required_after_step_id=forecast.required_after_step_id,
                    gate_type=forecast.gate_type,
                    planned_at=forecast.risk.planned_at,
                    forecast_at=forecast.forecast_at,
                    slack_minutes=forecast.risk.slack_minutes,
                    risk_level=forecast.risk.risk_level.name,
                )
                for forecast in result.gate_forecasts
            ],
            processes=[
                ProcessForecastResponse(
                    lot_id=forecast.lot_id,
                    process_code=forecast.process_code,
                    forecast_start=forecast.forecast_start,
                    forecast_end=forecast.forecast_end,
                    scheduled_operation_count=forecast.scheduled_operation_count,
                )
                for forecast in result.process_forecasts
            ],
            missing_gate_ids=list(result.missing_gate_ids),
            waiting_operation_ids=list(snapshot.waiting_operation_ids),
        )

    @app.post("/replan-candidates", response_model=ReplanCandidatesResponse)
    def create_replan_candidates(
        session: Annotated[Session, Depends(get_session)],
        as_of: datetime | None = None,
    ) -> ReplanCandidatesResponse:
        config = require_forecast_config()
        reference_time = resolve_reference_time(as_of)

        try:
            snapshot = build_replan_candidates(
                session=session,
                as_of=reference_time,
                config=config,
            )
        except (RuntimeError, ValueError) as exc:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=str(exc),
            ) from exc

        return ReplanCandidatesResponse(
            parent_plan_id=snapshot.parent_plan_id,
            parent_plan_version=snapshot.parent_plan_version,
            as_of=snapshot.as_of,
            risk_level=snapshot.risk_level.name,
            action=snapshot.action.value,
            recommended_candidate_id=snapshot.recommended_candidate_id,
            requires_manager_approval=snapshot.requires_manager_approval,
            candidates=[
                ReplanCandidateResponse(
                    candidate_id=candidate.candidate_id,
                    rule=candidate.rule.value,
                    kpi=CandidateKPIResponse(
                        late_lot_count=candidate.kpi.late_lot_count,
                        total_tardiness_minutes=(
                            candidate.kpi.total_tardiness_minutes
                        ),
                        overtime_minutes=candidate.kpi.overtime_minutes,
                        change_count=candidate.kpi.change_count,
                    ),
                    tasks=[
                        ReplanCandidateTaskResponse(
                            lot_id=task.lot_id,
                            routing_step_id=task.routing_step_id,
                            target_start=task.target_start,
                            target_end=task.target_end,
                            target_qty=task.target_qty,
                            priority_rank=task.priority_rank,
                        )
                        for task in candidate.tasks
                    ],
                )
                for candidate in snapshot.candidates
            ],
        )

    return app
