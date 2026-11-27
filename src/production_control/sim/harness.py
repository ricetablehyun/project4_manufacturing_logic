"""Wire one virtual plant to one production-control API instance."""

from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from fastapi import FastAPI
from fastapi.testclient import TestClient

from production_control.api.app import create_app
from production_control.persistence.database import (
    create_session_factory,
    create_sqlite_engine,
)
from production_control.persistence.live_forecast import LiveForecastConfig
from production_control.sim.manager import ApprovalPolicy
from production_control.sim.plant import VirtualPlant
from production_control.sim.runner import (
    ClockHolder,
    RunResult,
    build_plant_layout,
    load_plant_calendar,
    run_closed_loop,
)
from production_control.sim.terminal import HttpClient, ShopFloorTerminal
from production_control.sim.truth import TruthModel

DEFAULT_FORECAST_CONFIG = LiveForecastConfig(
    calendar_id="CALENDAR-NORMAL",
    pace_min_samples=3,
    warning_threshold_minutes=120,
)


@dataclass
class SimulationHarness:
    app: FastAPI
    terminal: ShopFloorTerminal
    plant: VirtualPlant
    clock: ClockHolder

    def run(self, policy: ApprovalPolicy, **kwargs: object) -> RunResult:
        return run_closed_loop(
            terminal=self.terminal,
            plant=self.plant,
            clock=self.clock,
            policy=policy,
            **kwargs,
        )


def build_harness(
    database_path: str | Path,
    *,
    truth: TruthModel,
    start_time: datetime,
    run_tag: str,
    forecast_config: LiveForecastConfig = DEFAULT_FORECAST_CONFIG,
    resend_every: int = 0,
    client_factory: Callable[[FastAPI], HttpClient] = TestClient,
) -> SimulationHarness:
    """Create the API on ``database_path`` with the plant's simulated clock.

    The API is reached only through ``client_factory(app)``: an in-process
    ``TestClient`` by default, which exercises the same FastAPI routing,
    validation and serialization as a network client.
    """

    engine = create_sqlite_engine(Path(database_path))
    session_factory = create_session_factory(engine)
    session = session_factory()
    try:
        layout = build_plant_layout(session)
        calendar = load_plant_calendar(session, forecast_config.calendar_id)
    finally:
        session.close()

    clock = ClockHolder(start_time)
    app = create_app(
        session_factory=session_factory,
        forecast_config=forecast_config,
        clock=clock,
    )
    terminal = ShopFloorTerminal(
        client_factory(app),
        run_tag=run_tag,
        resend_every=resend_every,
    )
    plant = VirtualPlant(layout=layout, calendar=calendar, truth=truth, clock=start_time)
    return SimulationHarness(app=app, terminal=terminal, plant=plant, clock=clock)
