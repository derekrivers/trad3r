"""Read-only research inventory; structural completeness is not qualification."""
from datetime import date, timedelta

from .calendar import session_bounds
from .data import coverage_report, load_sample
from .features import FEATURE_SCHEMA
from .strategy import STRATEGY_ID

AUDIT_SCHEMA = "research-inventory-v1"


def audit_sample(path, start, end):
    """Audit an explicit inclusive window, including days omitted by a manifest.

    Never runs a strategy or silently promotes engineering data to a holdout.
    External research gates are deliberately not satisfiable by this bar audit.
    """
    session_bounds(start)
    session_bounds(end)
    first, last = date.fromisoformat(start), date.fromisoformat(end)
    if first > last:
        raise ValueError("Research window start must not follow its end")
    sessions = []
    day = first
    while day <= last:
        if session_bounds(day.isoformat()) is not None:
            sessions.append(day.isoformat())
        day += timedelta(days=1)
    if not sessions:
        raise ValueError("Research window contains no supported exchange sessions")
    bars, source = load_sample(path)
    selected = [bar for bar in bars if start <= bar.session <= end]
    coverage = coverage_report(selected, source["symbols"], sessions)
    declared = sorted(next(iter(source["session_counts"].values())))
    missing_sessions = sorted(set(sessions) - set(declared))
    blockers = []
    if not coverage["complete"]:
        blockers.append(dict(code="requested_bar_coverage_incomplete",
                             required="Obtain all scheduled bars or resolve and document genuine market closures; do not fabricate bars."))
    blockers.extend([
        dict(code="history_not_qualified",
             required="Review provenance, rights, independent price checks, corporate actions and point-in-time universe selection."),
        dict(code="holdout_not_established",
             required="Register untouched chronological evaluation periods and an inspected-data exclusion list before viewing outcomes."),
        dict(code="fx_and_costs_not_qualified",
             required="Supply timestamped USD/GBP observations and sourced broker fees, FX conversion charges and spread/slippage assumptions."),
        dict(code="period_transition_not_approved",
             required="Owner review of the proposed period-transition workflow; current code never renews loss budgets."),
        dict(code="account_backtest_not_available",
             required="Implement and verify the approved transition workflow before evaluating a continuous multi-day account."),
    ])
    return dict(schema=AUDIT_SCHEMA, mode="offline_research_inventory_only",
                source_sha256=source["source_sha256"], calendar_id=source["calendar_id"],
                strategy_id=STRATEGY_ID, feature_schema=FEATURE_SCHEMA,
                window=dict(start=start, end=end, expected_sessions=len(sessions)),
                symbols=source["symbols"], selected_bars=len(selected),
                declared_coverage_complete=source["coverage"]["complete"],
                requested_coverage=coverage, sessions_absent_from_manifest=missing_sessions,
                structurally_complete=coverage["complete"], research_ready=False,
                live_trading_enabled=False, blockers=blockers,
                limitations="Bar-only inventory; no external gate verification, strategy outcomes, profitability assessment or holdout qualification.")
