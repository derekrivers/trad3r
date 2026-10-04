"""Frozen experimental hypothesis, not an established profitable strategy."""
from datetime import time, timedelta
from zoneinfo import ZoneInfo

from .features import FEATURE_SCHEMA, feature_snapshots

STRATEGY_ID = "orb30-one-share-v1"


def opening_range_signals(bars, symbol):
    """At most one long candidate from a contiguous single-session bar prefix.

    First positive-volume close crossing above the completed opening-range high.
    One share; stop at range low; target two reference price-risk units above close.
    The simulator independently rechecks affordability and risk at the later fill.
    """
    bars = list(bars)
    if not bars or any(b.symbol != symbol or b.session != bars[0].session for b in bars):
        raise ValueError("Opening-range hypothesis requires one symbol and session")
    frames = feature_snapshots(bars, [symbol])
    signals, previous = [], None
    for bar, frame in zip(bars, frames):
        row = frame["rows"][0]
        at = bar.available_at
        local = at.astimezone(ZoneInfo("America/New_York"))
        candidate_time = local + timedelta(minutes=1)
        if (not signals and row["opening_range_complete"] and
                time(10) <= local.time() < time(11, 30) and candidate_time.time() < time(11, 30) and
                previous <= row["opening_range_high"] < bar.close and bar.volume > 0):
            stop = row["opening_range_low"]
            signals.append(dict(id=f"{STRATEGY_ID}-{bar.session}-{symbol}",
                                at=at.isoformat(), quantity=1, stop=stop,
                                target=bar.close + 2 * (bar.close - stop)))
        previous = bar.close
    return dict(strategy_id=STRATEGY_ID, feature_schema=FEATURE_SCHEMA, symbol=symbol,
                session=bars[0].session, research_status="unvalidated_hypothesis",
                live_trading_enabled=False, signals=signals)
