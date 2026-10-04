"""Frozen single-symbol hypothesis over one bounded, continuous research account."""
from datetime import time
from zoneinfo import ZoneInfo

from .calendar import scheduled_sessions
from .features import FEATURE_SCHEMA
from .evaluation import summarize_run
from .simulation import simulate_research_series
from .strategy import STRATEGY_ID, opening_range_signals


def baseline_backtest(sessions, start, end):
    sessions = [(list(bars), scenario) for bars, scenario in sessions]
    expected = scheduled_sessions(start, end)
    if [scenario["session"] for _, scenario in sessions] != expected:
        raise ValueError("Baseline requires every scheduled session in the window, in order")
    if len({scenario["symbol"] for _, scenario in sessions}) != 1:
        raise ValueError("Frozen baseline requires one preselected symbol across the run")
    prepared = []
    for bars, scenario in sessions:
        if "signals" in scenario:
            raise ValueError("Omit supplied signals for the frozen baseline hypothesis")
        generated = opening_range_signals(bars, scenario["symbol"])
        if bars[-1].available_at.astimezone(ZoneInfo("America/New_York")).time() < time(12):
            raise ValueError("Baseline requires contiguous opening bars through the noon flatten deadline")
        prepared.append((bars, dict(scenario, signals=generated["signals"])))
    result = simulate_research_series(prepared, start, end, strategy_id=STRATEGY_ID)
    result.update(mode="offline_baseline_backtest_only", feature_schema=FEATURE_SCHEMA,
                  hypothesis_status="unvalidated_hypothesis")
    for session, (_, scenario) in zip(result["sessions"], prepared):
        session["generated_signals"] = scenario["signals"]
    reference = simulate_research_series([(bars, dict(scenario, signals=[])) for bars, scenario in prepared],
                                        start, end, strategy_id="no-trade-same-cash-v1")
    for session in reference["sessions"]:
        session["generated_signals"] = []
    result["evaluation"] = summarize_run(result)
    reference["evaluation"] = summarize_run(reference)
    result["cash_reference"] = reference
    result["comparison"] = dict(reference_id="no-trade-same-cash-v1",
                                net_account_pnl_difference_gbp=result["final_ledger"]["account_pnl_gbp"]-
                                reference["final_ledger"]["account_pnl_gbp"])
    return result
