"""Shipping-inspection duration rule (V1, confirmed for the midterm demo).

Shipping inspection lasts 3 business days (Saturday and Sunday excluded) and
the start day counts as day 1: a Monday start finishes Wednesday 17:00. The
dashboard and the experiment's final-due metric both use this one rule.
"""

from datetime import datetime, time, timedelta

SHIPPING_INSPECTION_BUSINESS_DAYS = 3
SHIPPING_INSPECTION_WORKDAY_END = time(17, 0)
ACTIVE_WEEKDAYS = frozenset({0, 1, 2, 3, 4})


def shipping_inspection_expected_finish(planned_start: datetime) -> datetime:
    """Return end of the third weekday, counting the inspection start day.

    The confirmed V1 rule excludes Saturday/Sunday only.  For example, an
    inspection starting Monday finishes at Wednesday 17:00; a Friday start
    finishes at Tuesday 17:00.
    """

    if planned_start.tzinfo is None or planned_start.utcoffset() is None:
        raise ValueError("planned_start must be timezone-aware")

    current_date = planned_start.date()
    counted = 0
    while counted < SHIPPING_INSPECTION_BUSINESS_DAYS:
        if current_date.weekday() in ACTIVE_WEEKDAYS:
            counted += 1
            if counted == SHIPPING_INSPECTION_BUSINESS_DAYS:
                return datetime.combine(
                    current_date,
                    SHIPPING_INSPECTION_WORKDAY_END,
                    tzinfo=planned_start.tzinfo,
                )
        current_date += timedelta(days=1)

    raise RuntimeError("unreachable inspection completion calculation")
