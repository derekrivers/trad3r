"""Bounded US cash-equity session schedule; never a settlement calendar.

Sources and refresh contract: docs/calendar.md. Unknown years fail closed.
"""
from datetime import date, datetime, time, timedelta, timezone
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError


CALENDAR_ID = "us-equities-2026-reviewed-2026-10-04"
HOLIDAYS = frozenset({
    "2026-01-01", "2026-01-19", "2026-02-16", "2026-04-03",
    "2026-05-25", "2026-06-19", "2026-07-03", "2026-09-07",
    "2026-11-26", "2026-12-25",
})
EARLY_CLOSES = frozenset({"2026-11-27", "2026-12-24"})


def session_bounds(session):
    """UTC [open, close) bounds, or None for a scheduled closed day in 2026."""
    if not isinstance(session, str):
        raise ValueError("Session date must be YYYY-MM-DD")
    day = date.fromisoformat(session)
    if day.isoformat() != session:
        raise ValueError("Session date must be YYYY-MM-DD")
    if day.year != 2026:
        raise ValueError("Exchange calendar supports 2026 only; review required")
    if day.weekday() >= 5 or session in HOLIDAYS:
        return None
    try:
        zone = ZoneInfo("America/New_York")
    except ZoneInfoNotFoundError as error:
        raise ValueError("New York timezone data unavailable; install tzdata") from error
    close = time(13) if session in EARLY_CLOSES else time(16)
    return tuple(datetime.combine(day, clock, zone).astimezone(timezone.utc)
                 for clock in (time(9, 30), close))


def validate_minute(start, session):
    """Require a whole UTC minute fully inside its declared regular session."""
    if start.tzinfo is None or start.utcoffset() != timedelta(0) or start.second or start.microsecond:
        raise ValueError("Bar timestamp must be minute-aligned UTC")
    bounds = session_bounds(session)
    if bounds is None or not bounds[0] <= start < bounds[1]:
        raise ValueError("Bar is outside scheduled regular trading hours for its session date")
