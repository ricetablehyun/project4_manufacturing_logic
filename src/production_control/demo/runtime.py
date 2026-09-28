"""Factory for a FastAPI app backed by an explicitly initialized demo DB."""

from pathlib import Path

from fastapi import FastAPI

from production_control.api.app import create_app
from production_control.demo.bootstrap import DEFAULT_DEMO_DB_PATH
from production_control.persistence.database import (
    create_session_factory,
    create_sqlite_engine,
)
from production_control.persistence.live_forecast import LiveForecastConfig


def create_demo_app(path: str | Path = DEFAULT_DEMO_DB_PATH) -> FastAPI:
    """Bind the existing API to the local/demo SQLite database."""

    database_path = Path(path)
    if not database_path.is_file():
        raise FileNotFoundError(
            "demo database is not initialized: "
            f"{database_path}. Run `python -m production_control.demo.init_db --reset`."
        )

    engine = create_sqlite_engine(database_path)
    session_factory = create_session_factory(engine)
    app = create_app(
        session_factory=session_factory,
        forecast_config=LiveForecastConfig(
            calendar_id="CALENDAR-NORMAL",
            pace_min_samples=3,
            warning_threshold_minutes=120,
        ),
    )
    app.state.demo_database_path = database_path
    app.state.demo_engine = engine
    return app
