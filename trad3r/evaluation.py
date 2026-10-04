"""Descriptive engineering metrics, never a statistical validation verdict."""
from collections import Counter
from decimal import Decimal as D

from .ledger import Ledger, utc
from .risk import Policy, money

REPORT_SCHEMA = "account-evaluation-v1"


def summarize_run(result):
    """Reconstruct generated-run accounting rather than summing daily snapshots."""
    book = Ledger()
    curve, trades = [], []
    initial = Policy().initial_capital
    peak, minimum, drawdown = initial, initial, D(0)
    commissions, conversion_fees, turnover = D(0), D(0), D(0)
    entry_at, realised_before, exposure_seconds, entries = None, D(0), 0, 0
    for event in result["ledger_events"]:
        kind = event["type"]
        if kind == "buy" and book.position is None:
            entry_at, realised_before = event["at"], book.realised_trade_pnl
            entries += 1
        book.apply(event)
        if kind in ("buy", "sell"):
            fx = money(event["usd_to_gbp"])
            commissions += money(event["fee_usd"]) * fx
            turnover += event["quantity"] * money(event["price"]) * fx
        elif kind == "exchange":
            conversion_fees += money(event["fee_gbp"])
        if kind == "sell" and book.position is None:
            elapsed = int((utc(event["at"]) - utc(entry_at)).total_seconds())
            exposure_seconds += elapsed
            trades.append(dict(entry_at=entry_at, exit_at=event["at"],
                               realised_trade_pnl_gbp=book.realised_trade_pnl-realised_before))
            entry_at = None
        if kind == "value":
            value = book.last_report
            adjusted = value["equity_gbp"] - value["deposits_gbp"] + value["withdrawals_gbp"]
            peak, minimum = max(peak, adjusted), min(minimum, adjusted)
            drawdown = max(drawdown, peak-adjusted)
            curve.append(dict(ledger_event_id=event["id"], at=event["at"],
                              equity_gbp=value["equity_gbp"], adjusted_equity_gbp=adjusted,
                              account_pnl_gbp=value["account_pnl_gbp"]))
    if not curve or book.position is not None or book.last_report != result["final_ledger"]:
        raise ValueError("Evaluation requires a reconciled final flat account valuation")
    sessions = result["sessions"]
    checks = [e for s in sessions for e in s["trace"] if e["type"] == "entry_check"]
    rejected = [e for e in checks if not e["eligible"]]
    reasons = Counter(reason for e in rejected for reason in e["reasons"])
    exits = Counter(e["reason"] for s in sessions for e in s["trace"] if e["type"] == "exit")
    wins = sum(t["realised_trade_pnl_gbp"] > 0 for t in trades)
    losses = sum(t["realised_trade_pnl_gbp"] < 0 for t in trades)
    pnl = book.last_report["account_pnl_gbp"]
    return dict(schema=REPORT_SCHEMA, research_status="engineering_scenario_only",
                sessions=len(sessions), candidates=sum(len(s["generated_signals"]) for s in sessions),
                no_candidate_sessions=sum(not s["generated_signals"] for s in sessions),
                sessions_blocked_at_end=sum(bool(s["blocked_reasons"]) for s in sessions),
                entries=entries, closed_trades=len(trades), rejected_candidates=len(rejected),
                expired_candidates=sum(e["type"] == "expired_signal" for s in sessions for e in s["trace"]),
                rejection_reason_counts=dict(sorted(reasons.items())), exit_reason_counts=dict(sorted(exits.items())),
                winning_trades=wins, losing_trades=losses, breakeven_trades=len(trades)-wins-losses,
                trade_win_fraction=None if not trades else D(wins)/len(trades),
                net_account_pnl_gbp=pnl, net_account_return=pnl/initial,
                realised_trade_pnl_gbp=book.realised_trade_pnl,
                max_observed_drawdown_gbp=drawdown, max_observed_loss_from_initial_gbp=initial-minimum,
                explicit_commissions_gbp=commissions, explicit_conversion_fees_gbp=conversion_fees,
                gross_turnover_gbp=turnover, simulated_position_seconds=exposure_seconds,
                equity_curve=curve, trades=trades,
                limitations="Observed valuations only; gaps/unobserved price paths are not inferred. Fees and modelled fills already affect P&L; no profitability or statistical-confidence verdict.")
