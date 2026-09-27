"""FastAPI boundary for the production-control system."""

from production_control.api.app import create_app

__all__ = ["create_app"]
