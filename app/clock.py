"""Single source of "today" for date-based rules (return windows, refund timing)."""

from datetime import date

from app.config.settings import get_settings
from app.database.seed import REFERENCE_DATE


def today() -> date:
    return get_settings().demo_today or REFERENCE_DATE
