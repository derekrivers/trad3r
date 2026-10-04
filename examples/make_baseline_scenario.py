"""Print a deliberately synthetic two-day fixture, never market-performance data."""
from datetime import timedelta
import json

from trad3r.calendar import session_bounds


def fixture():
    sessions = []
    for day in ("2026-09-08", "2026-09-09"):
        opening, _ = session_bounds(day)
        bars = []
        for minute in range(150):
            price = 100 if minute < 30 else 102
            bars.append(dict(symbol="SYNTH", currency="USD", session_date=day,
                             timestamp_utc=(opening+timedelta(minutes=minute)).isoformat(),
                             o=price, h=101 if minute < 30 else price, l=price, c=price, v=1000))
        scenario = dict(symbol="SYNTH", session=day, bars=bars,
                        fx=[dict(at=b["timestamp_utc"], usd_to_gbp="0.8") for b in bars],
                        costs=dict(entry_fee_usd="0.5", exit_fee_usd="0.5", slippage_usd_per_share="0.05"))
        if not sessions:
            scenario["funding"] = dict(amount="400", received="500", fee_gbp="0")
        sessions.append(scenario)
    return dict(window=dict(start="2026-09-08", end="2026-09-09"), sessions=sessions)


if __name__ == "__main__":
    print(json.dumps(fixture(), sort_keys=True, indent=2))
