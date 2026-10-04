"""Scheduled regular-way US equity settlement, bounded to reviewed 2026 dates.

Cash availability is a separate offline modelling policy; see docs/settlement.md.
"""
from datetime import date, datetime, time, timedelta, timezone
from zoneinfo import ZoneInfo

from .calendar import session_bounds


SETTLEMENT_CALENDAR_ID = "us-equity-t1-2026-reviewed-2026-10-04"
CASH_RELEASE_POLICY = "explicit-event-after-settlement-day-new-york-v1"
# Separate from exchange hours: banks can close while equities still trade.
# Limited DTC processing on Good Friday / July 3 is not regular-way CNS settlement.
NON_SETTLEMENT_DAYS = frozenset({
    "2026-01-01", "2026-01-19", "2026-02-16", "2026-04-03",
    "2026-05-25", "2026-06-19", "2026-07-03", "2026-09-07",
    "2026-10-12", "2026-11-11", "2026-11-26", "2026-12-25",
})


def is_settlement_day(day):
    if type(day) is not date or day.year != 2026:
        raise ValueError("Settlement calendar supports 2026 dates only; review required")
    return day.weekday() < 5 and day.isoformat() not in NON_SETTLEMENT_DAYS


def settlement_date(trade_session):
    """Next scheduled settlement business day after an exchange trade date."""
    if session_bounds(trade_session) is None:
        raise ValueError("Trade date is not a scheduled exchange session")
    due = date.fromisoformat(trade_session) + timedelta(days=1)
    while not is_settlement_day(due):
        due += timedelta(days=1)
    return due


def validate_settlement(trade_session, supplied):
    """A supplied date is an assertion, never an override of the calendar."""
    due = settlement_date(trade_session)
    if supplied != due.isoformat():
        raise ValueError("settles_on must match scheduled T+1 date " + due.isoformat())
    return due


def cash_available_at(due):
    """Conservative research cutoff, NOT a broker's actual cash availability."""
    if not is_settlement_day(due):
        raise ValueError("Cash release requires a scheduled settlement date")
    following_day = due + timedelta(days=1)
    return datetime.combine(following_day, time(), ZoneInfo("America/New_York")).astimezone(timezone.utc)
