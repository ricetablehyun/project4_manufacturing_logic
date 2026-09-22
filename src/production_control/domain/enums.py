"""Domain enumerations for shop-floor execution."""

from enum import StrEnum


class OperationState(StrEnum):
    """V1 UnitOperation execution states."""

    WAITING = "WAITING"
    RUNNING = "RUNNING"
    HOLD = "HOLD"
    COMPLETED = "COMPLETED"
