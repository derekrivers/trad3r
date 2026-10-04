"""Pure entry diagnostics; never an order reservation or live authorisation."""
from datetime import time, timedelta
from decimal import Decimal as D
from zoneinfo import ZoneInfo

from .ledger import Ledger, nonnegative, positive, shares, utc
from .risk import Mark, Policy, money, planned_long_loss


def check_entry(ledger: Ledger, risk: dict, proposal: dict, at: str, attempts: int):
    """Evaluate a long entry against coherent snapshots and conservative costs.

    attempts is the number already attempted in this session (not just fills).
    This function changes no state; the simulator must increment it atomically.
    """
    now = utc(at)
    if type(attempts) is not int or attempts < 0:
        raise ValueError("Entry attempt count must be a nonnegative integer")
    required = {"symbol", "quantity", "entry", "stop", "entry_fee_usd", "exit_fee_usd",
                "slippage_usd_per_share", "usd_to_gbp", "quote_at", "fx_at"}
    if not isinstance(proposal, dict) or set(proposal) != required:
        raise ValueError("Entry proposal fields do not match the contract")
    symbol = proposal["symbol"]
    if not isinstance(symbol, str) or not symbol.isalnum():
        raise ValueError("Invalid symbol")
    quantity = shares(proposal["quantity"])
    entry, stop, fx = map(positive, (proposal["entry"], proposal["stop"], proposal["usd_to_gbp"]))
    if stop >= entry:
        raise ValueError("Long stop must be below the reference entry price")
    entry_fee, exit_fee, slip = map(nonnegative, (proposal["entry_fee_usd"],
                                                 proposal["exit_fee_usd"], proposal["slippage_usd_per_share"]))
    loss = planned_long_loss(quantity, entry + slip, stop - slip, fx, (entry_fee + exit_fee) * fx)
    if ledger.last_report is None:
        raise ValueError("A current ledger valuation is required")
    value = ledger.last_report
    if risk["mode"] != "offline_risk_observations_only" or risk["live_trading_enabled"] is not False:
        raise ValueError("Expected an offline risk status")
    if type(risk["blocked"]) is not bool or not isinstance(risk["blocked_reasons"], list):
        raise ValueError("Invalid risk status")
    mark = Mark(value["equity_gbp"], value["deposits_gbp"], value["withdrawals_gbp"])
    if utc(value["as_of"]) != utc(risk["as_of"]) or mark != Mark(**risk["mark"]):
        raise ValueError("Ledger and risk observations do not match")
    if money(value["usd_to_gbp"]) != fx:
        raise ValueError("Ledger and proposal FX do not match")
    reasons = []
    if risk["blocked"] or risk["blocked_reasons"]:
        reasons.append("risk_blocked")
    for name, stamp in (("valuation", value["as_of"]), ("quote", proposal["quote_at"]),
                        ("fx", proposal["fx_at"])):
        age = now - utc(stamp)
        if not timedelta(0) <= age <= timedelta(seconds=60):
            reasons.append(name + "_stale_or_future")
    local = now.astimezone(ZoneInfo("America/New_York"))
    if local.date().isoformat() != risk["baseline_session"]:
        reasons.append("period_review_required")
    if local.weekday() >= 5 or not time(10) <= local.time() < time(11, 30):
        reasons.append("outside_entry_window")
    if ledger.position is not None:
        reasons.append("position_already_open")
    if attempts >= 3:
        reasons.append("entry_attempt_limit")
    notional = quantity * (entry + slip) * fx
    cash_required = quantity * (entry + slip) + entry_fee + exit_fee
    if notional > D("500"):
        reasons.append("exposure_limit")
    if cash_required > ledger.cash["USD"]:
        reasons.append("insufficient_settled_cash")
    if loss > Policy().trade_loss:
        reasons.append("trade_loss_limit")
    pnl = risk["assessment"]
    for name, field, limit in (("overall", "cumulative_pnl", Policy().overall_loss),
                               ("daily", "daily_pnl", Policy().daily_loss),
                               ("weekly", "weekly_pnl", Policy().weekly_loss)):
        if loss > limit + money(pnl[field]):
            reasons.append(name + "_loss_headroom")
    return {"mode": "offline_entry_diagnostic_only", "eligible": not reasons,
            "reasons": sorted(set(reasons)), "planned_loss_gbp": loss,
            "notional_gbp": notional, "cash_required_usd": cash_required,
            "attempts_before": attempts, "live_trading_enabled": False}
