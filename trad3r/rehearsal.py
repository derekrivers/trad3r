"""Executable synthetic control drill; never a broker paper trading session."""
from pathlib import Path

from .admission import check_entry
from .experiments import canonical, code_fingerprint, digest, _publish
from .ledger import Ledger, replay_ledger
from .risk import money
from . import risk_store

AT = "2026-09-08T14:00:00Z"
SCHEMA = "offline-control-rehearsal-v1"


def rehearse_controls(directory):
    directory = Path(directory)
    # Exclusive directory creation prevents accidental reuse of any account store.
    directory.mkdir(mode=0o700, parents=False, exist_ok=False)
    database = directory/"synthetic-risk.sqlite"
    risk_store.initialize(database, "2026-09-08T13:59:00Z")
    book, events, checks = Ledger(), [], []

    def event(value):
        book.apply(value)
        events.append(value)

    def require(identity, passed, observed):
        if passed is not True:
            raise ValueError("Control rehearsal failed: " + identity)
        checks.append(dict(id=identity, passed=True, observed=observed))

    event(dict(id="fund", type="fund", at=AT, amount="1000"))
    event(dict(id="exchange", type="exchange", at=AT, from_currency="GBP", amount="400",
               received="500", fee_gbp="0"))
    event(dict(id="opening-value", type="value", at=AT, usd_to_gbp="0.8", prices={}))
    current = risk_store.record(database, risk_store.from_ledger("opening", book.last_report), 0)
    proposal = dict(symbol="SYNTH", quantity=1, entry="100", stop="99", entry_fee_usd="0.5",
                    exit_fee_usd="0.5", slippage_usd_per_share="0.05", usd_to_gbp="0.8",
                    quote_at=AT, fx_at=AT)
    before = canonical(book.last_report)
    initial = check_entry(book, current, proposal, AT, 0)
    require("coherent_synthetic_entry_eligible", initial["eligible"] is True, initial)
    cases = [
        ("trade_budget", dict(stop="95"), AT, 0, "trade_loss_limit"),
        ("exposure", dict(entry="626", stop="625"), AT, 0, "exposure_limit"),
        ("settled_cash", dict(entry="501", stop="500"), AT, 0, "insufficient_settled_cash"),
        ("attempts", {}, AT, 3, "entry_attempt_limit"),
        ("stale_quote", dict(quote_at="2026-09-08T13:58:59Z"), AT, 0, "quote_stale_or_future"),
        ("future_quote", dict(quote_at="2026-09-08T14:00:01Z"), AT, 0, "quote_stale_or_future"),
        ("stale_fx", dict(fx_at="2026-09-08T13:58:59Z"), AT, 0, "fx_stale_or_future"),
        ("stale_valuation", {}, "2026-09-08T14:01:01Z", 0, "valuation_stale_or_future"),
    ]
    for identity, changes, at, attempts, reason in cases:
        result = check_entry(book, current, dict(proposal, **changes), at, attempts)
        require(identity+"_rejected", result["eligible"] is False and reason in result["reasons"], result)
    require("diagnostics_do_not_reserve_or_fill", canonical(book.last_report) == before
            and book.position is None and risk_store.status(database)["version"] == 1,
            dict(position=book.position, risk_version=1, generated_orders=0))

    # Deliberately extreme synthetic cash FX shock: GBP600 + USD500 * .2 = GBP700.
    # This exercises account-level loss, including cash FX, without faking a fill.
    event(dict(id="loss-value", type="value", at="2026-09-08T14:01:00Z", usd_to_gbp="0.2", prices={}))
    loss = risk_store.record(database, risk_store.from_ledger("loss", book.last_report), 1)
    halts = {"overall", "daily", "weekly"}
    require("exact_300_account_loss_halts", set(loss["assessment"]["halt_reasons"]) == halts
            and money(loss["mark"]["equity"]) == 700, loss)
    reopened = risk_store.status(database)
    require("reopened_store_retains_halts", canonical(reopened) == canonical(loss), reopened)
    event(dict(id="recovery-value", type="value", at="2026-09-08T14:02:00Z", usd_to_gbp="0.8", prices={}))
    recovered = risk_store.record(database, risk_store.from_ledger("recovery", book.last_report), 2)
    require("price_recovery_does_not_clear_halts", recovered["blocked"] is True
            and set(recovered["assessment"]["halt_reasons"]) == halts, recovered)
    request = dict(proposal, quote_at=recovered["as_of"], fx_at=recovered["as_of"])
    result = check_entry(book, recovered, request, recovered["as_of"], 0)
    require("halt_blocks_fresh_entry", result["eligible"] is False and "risk_blocked" in result["reasons"], result)
    event(dict(id="next-day-value", type="value", at="2026-09-09T14:00:00Z", usd_to_gbp="0.8", prices={}))
    final = risk_store.record(database, risk_store.from_ledger("next-day", book.last_report), 3)
    require("next_day_never_renews_durable_budget", final["blocked"] is True
            and set(final["blocked_reasons"]) == halts | {"period_review_required"}
            and final["baseline_session"] == "2026-09-08", final)
    require("ledger_reconciles", canonical(replay_ledger(events)) == canonical(book.last_report), book.last_report)
    require("risk_history_retained", len(risk_store.history(database)) == 4,
            dict(observations=4, final_version=final["version"]))
    journal_raw = canonical(events)
    _publish(journal_raw, directory/"synthetic-ledger-events.json")
    report = dict(schema=SCHEMA, mode="synthetic_offline_control_rehearsal", code_sha256=code_fingerprint(),
                  checks=checks, passed=True, journal_sha256=digest(journal_raw), final_risk=final,
                  generated_orders=0, broker_connected=False, paper_ready=False, live_trading_enabled=False,
                  limitations="Fixed synthetic dates, quotes and cash FX shock; no broker, feed, orders or performance qualification.")
    _publish(canonical(report), directory/"rehearsal-report.json")
    return report
