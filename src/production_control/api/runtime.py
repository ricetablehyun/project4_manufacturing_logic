"""Uvicorn entrypoint for the explicitly initialized local/demo database."""

import os
from datetime import time
from pathlib import Path

from production_control.demo.bootstrap import DEFAULT_DEMO_DB_PATH
from production_control.demo.runtime import create_demo_app

_database_path = Path(
    os.environ.get("PRODUCTION_CONTROL_DB_PATH", str(DEFAULT_DEMO_DB_PATH))
)

# Weekday overtime candidates (D078) are off unless an end time is given,
# e.g. PRODUCTION_CONTROL_OVERTIME_END=19:00.
_overtime_end_text = os.environ.get("PRODUCTION_CONTROL_OVERTIME_END", "").strip()
_overtime_end = time.fromisoformat(_overtime_end_text) if _overtime_end_text else None

app = create_demo_app(_database_path, overtime_end=_overtime_end)
