"""Thin FastAPI boundary over the persisted WorkEvent service."""

from collections.abc import Iterator
from datetime import UTC, datetime
from typing import Annotated

from fastapi import Depends, FastAPI, HTTPException, Response, status
from sqlalchemy.orm import Session, sessionmaker

from production_control.api.models import WorkEventRequest, WorkEventResponse
from production_control.core.execution_state import WorkEventInput
from production_control.persistence.execution_service import persist_work_event


def create_app(*, session_factory: sessionmaker[Session]) -> FastAPI:
    """Create the API without inventing deployment-time database configuration."""

    app = FastAPI(title="Production Control API")

    def get_session() -> Iterator[Session]:
        session = session_factory()
        try:
            yield session
        finally:
            session.close()

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

    return app
