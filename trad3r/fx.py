"""Validate explicitly modelled completed-minute historical FX observations."""
from datetime import timedelta
from decimal import Decimal, localcontext

from .data import decode
from .ledger import positive, utc

FX_MODEL = "historical-completed-bar-proxy-v1"


def completed_fx(raw):
    observations, previous = [], None
    for line in raw.splitlines():
        row = decode(line)
        if (not isinstance(row, dict) or set(row) != {"bar_start", "at", "gbp_usd_close", "usd_to_gbp", "model"}
                or row["model"] != FX_MODEL):
            raise ValueError("Unsupported completed FX record")
        start, at = utc(row["bar_start"]), utc(row["at"])
        if start.second or start.microsecond or at != start+timedelta(minutes=1):
            raise ValueError("FX availability must be exactly the whole minute's completion")
        if previous is not None and at <= previous:
            raise ValueError("FX records must be unique and chronological")
        close, rate = positive(row["gbp_usd_close"]), positive(row["usd_to_gbp"])
        with localcontext() as context:
            context.prec = 28
            expected = Decimal(1)/close
        if rate != expected:
            raise ValueError("FX rate does not match the declared GBP/USD inverse close")
        observations.append((at, dict(at=at.isoformat(), usd_to_gbp=str(rate))))
        previous = at
    if not observations:
        raise ValueError("Completed FX observations are empty")
    return observations
