"""Uvicorn entrypoint for the explicitly initialized local/demo database."""

import os
from pathlib import Path

from production_control.demo.bootstrap import DEFAULT_DEMO_DB_PATH
from production_control.demo.runtime import create_demo_app

_database_path = Path(
    os.environ.get("PRODUCTION_CONTROL_DB_PATH", str(DEFAULT_DEMO_DB_PATH))
)

app = create_demo_app(_database_path)
