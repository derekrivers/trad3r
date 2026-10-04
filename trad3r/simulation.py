"""Offline session/series scenarios, not a strategy or broker emulator."""
from bisect import bisect_right
from dataclasses import asdict, dataclass, field
from datetime import time, timedelta
import hashlib
import json
from zoneinfo import ZoneInfo

from .admission import check_entry
from .calendar import CALENDAR_ID, scheduled_sessions, validate_minute
from .ledger import Ledger, nonnegative, positive, shares, utc
from .risk import Mark, Policy, assess
from .settlement import SETTLEMENT_CALENDAR_ID, settlement_date, validate_settlement

ROLLOVER_POLICY = "offline-unhalted-period-rollover-v1"


def bracket_exit(bar, stop, target, slip):
    """Opening gaps precede intraminute ambiguity; targets get no gap improvement."""
    if bar.open <= stop:
        return bar.open - slip, "stop_gap"
    if bar.open >= target:
        return target - slip, "target_gap"
    if bar.low <= stop:
        return stop - slip, "stop_ambiguous" if bar.high >= target else "stop"
    if bar.high >= target:
        return target - slip, "target"
    return None


@dataclass
class _RunState:
    book: Ledger = field(default_factory=Ledger)
    events: list = field(default_factory=list)
    latched: tuple = ()
    baseline_session: str | None = None
    baseline_week: str | None = None
    session_start: Mark = field(default_factory=lambda: Mark(Policy().initial_capital))
    week_start: Mark = field(default_factory=lambda: Mark(Policy().initial_capital))
    rollover: bool = False
    transitions: list = field(default_factory=list)


def simulate(bars, scenario):
    """Run one isolated research session; never reset a durable risk account."""
    return _run_session(bars, scenario, _RunState())


def simulate_series(sessions):
    """Run ordered (bars, scenario) pairs against ONE isolated research account.

    Period changes block new entries, never automatically renew risk budgets.
    No partial result escapes if any session fails; supplied inputs are unchanged.
    """
    return _run_series(sessions, _RunState())


def simulate_research_series(sessions, start, end, *, strategy_id):
    """Owner-approved rollover exception for bounded, isolated in-memory runs.

    No durable risk store, external account, pending order queue or halt reset.
    Missing sessions are reported, never fabricated. All inputs precede success.
    """
    if (not isinstance(strategy_id, str) or not 1 <= len(strategy_id) <= 128 or
            any(not c.isascii() or not (c.isalnum() or c in "-_.") for c in strategy_id)):
        raise ValueError("Research requires an explicit versioned strategy/scenario identifier")
    expected = scheduled_sessions(start, end)
    sessions = [(list(bars), scenario) for bars, scenario in sessions]
    days = [scenario["session"] for _, scenario in sessions]
    if any(day not in expected for day in days):
        raise ValueError("Research session outside the explicit supported window")
    inputs = dict(window=dict(start=start, end=end), policy=ROLLOVER_POLICY, strategy_id=strategy_id,
                  signal_schema="supplied-signals-v1",
                  sessions=[dict(bars=[bar.event() for bar in bars], scenario=scenario)
                            for bars, scenario in sessions])
    identity = hashlib.sha256(json.dumps(inputs, default=str, sort_keys=True,
                                        separators=(",", ":"), allow_nan=False).encode()).hexdigest()
    state = _RunState(rollover=True)
    result = _run_series(sessions, state)
    result.update(mode="offline_research_series_only", rollover_policy=ROLLOVER_POLICY, strategy_id=strategy_id,
                  signal_schema="supplied-signals-v1",
                  window=dict(start=start, end=end), inputs_sha256=identity,
                  missing_sessions=sorted(set(expected)-set(days)),
                  transitions=state.transitions, research_status="engineering_scenario_only")
    return result


def _run_series(sessions, state):
    sessions = list(sessions)
    days = [scenario["session"] for _, scenario in sessions]
    if not days or days != sorted(set(days)):
        raise ValueError("Series sessions must be nonempty, unique and chronological")
    results = []
    for bars, scenario in sessions:
        result = _run_session(bars, scenario, state)
        # One complete ledger journal belongs to the account, not one per day.
        result.pop("ledger_events")
        results.append(result)
    return dict(mode="offline_series_simulation_only", live_trading_enabled=False,
                sessions=results, final_ledger=state.book.last_report,
                ledger_events=state.events, halt_reasons=list(state.latched),
                baseline_session=state.baseline_session, baseline_week=state.baseline_week,
                blocked_reasons=results[-1]["blocked_reasons"],
                calendar_id=CALENDAR_ID, settlement_calendar_id=SETTLEMENT_CALENDAR_ID)


def _run_session(bars, scenario, state):
    symbol, session = scenario["symbol"], scenario["session"]
    zone = ZoneInfo("America/New_York")
    bars = list(bars)
    if not bars or any(b.symbol != symbol or b.session != session for b in bars):
        raise ValueError("Simulation requires exactly one symbol and session")
    for bar in bars:
        validate_minute(bar.start, session)
    if any(b.start != a.available_at for a, b in zip(bars, bars[1:])):
        raise ValueError("Simulation bars must be contiguous and chronological")
    bars = [b for b in bars if b.start.astimezone(zone).time() < time(12)]
    if not bars:
        raise ValueError("No bars before the noon flatten deadline")
    due = (validate_settlement(session, scenario["settles_on"]) if "settles_on" in scenario
           else settlement_date(session))
    costs = scenario["costs"]
    if set(costs) != {"entry_fee_usd", "exit_fee_usd", "slippage_usd_per_share"}:
        raise ValueError("Explicit execution costs are required")
    entry_fee, exit_fee, slip = (nonnegative(costs[key]) for key in
                                ("entry_fee_usd", "exit_fee_usd", "slippage_usd_per_share"))
    observations = [(utc(row["at"]), positive(row["usd_to_gbp"])) for row in scenario["fx"]]
    times = [at for at, _ in observations]
    if not times or times != sorted(set(times)):
        raise ValueError("FX observations must be unique and chronological")

    def fx_at(at):
        index = bisect_right(times, at) - 1
        if index < 0 or at - times[index] > timedelta(seconds=60):
            raise ValueError("Missing or stale FX observation in simulation")
        return observations[index]

    available = {bar.available_at for bar in bars}
    signals = []
    for row in scenario["signals"]:
        if set(row) != {"id", "at", "quantity", "stop", "target"}:
            raise ValueError("Signal fields do not match the contract")
        identity, at = row["id"], utc(row["at"])
        if not isinstance(identity, str) or not identity or at not in available:
            raise ValueError("Signal must reference a completed bar in the supplied session")
        stop, target = positive(row["stop"]), positive(row["target"])
        if not slip < stop < target:
            raise ValueError("Invalid signal bracket")
        signals.append(dict(id=identity, at=at, quantity=shares(row["quantity"]), stop=stop, target=target))
    if len({s["id"] for s in signals}) != len(signals) or [s["at"] for s in signals] != sorted(s["at"] for s in signals):
        raise ValueError("Signals must have unique IDs and chronological timestamps")
    book, events, trace = state.book, state.events, []
    active, cursor, attempts = None, 0, 0
    if book.position is not None:
        raise ValueError("Series cannot carry an open position between sessions")
    if book.funded and "funding" in scenario:
        raise ValueError("Only the first series session may contain funding")

    def emit(kind, at, **fields):
        event = dict(id=f"sim-{len(events)}", type=kind, at=at.isoformat(), **fields)
        book.apply(event)
        events.append(event)

    def value(at, price):
        fx_time, fx = fx_at(at)
        emit("value", at, usd_to_gbp=fx, prices={symbol: price} if book.position else {})
        report = book.last_report
        mark = Mark(report["equity_gbp"], report["deposits_gbp"], report["withdrawals_gbp"])
        assessment = assess(mark, state.session_start, state.week_start, state.latched)
        state.latched = assessment.halt_reasons
        blocked = list(state.latched)
        if session != state.baseline_session:
            blocked.append("period_review_required")
        risk = dict(mode="offline_risk_observations_only", live_trading_enabled=False,
                    as_of=report["as_of"], mark=asdict(mark), baseline_session=state.baseline_session,
                    baseline_week=state.baseline_week,
                    assessment=asdict(assessment), blocked=bool(blocked), blocked_reasons=sorted(blocked))
        return risk, fx_time, fx

    def sell(at, price, reason):
        nonlocal active
        _, fx = fx_at(at)
        quantity = book.position.quantity
        emit("sell", at, symbol=symbol, quantity=quantity, price=positive(price),
             fee_usd=exit_fee, usd_to_gbp=fx, settles_on=due.isoformat())
        trace.append(dict(type="exit", at=at.isoformat(), signal=active["id"],
                          price=price, quantity=quantity, reason=reason))
        active = None

    start = bars[0].start
    if not book.funded:
        local = start.astimezone(zone).date()
        state.baseline_session = session
        state.baseline_week = (local - timedelta(days=local.weekday())).isoformat()
        emit("fund", start, amount=Policy().initial_capital)
        emit("exchange", start, from_currency="GBP", **scenario["funding"])
    else:
        emit("settle", start)
    for index, bar in enumerate(bars):
        risk, fx_time, fx = value(bar.start, bar.open)
        if index == 0 and state.rollover and session != state.baseline_session:
            # The fresh mark has ALREADY been assessed against the old baselines.
            # This engine has no pending orders and rejects overnight positions.
            mark = Mark(**risk["mark"])
            local = bar.start.astimezone(zone).date()
            week = (local - timedelta(days=local.weekday())).isoformat()
            before = dict(session=state.baseline_session, week=state.baseline_week,
                          session_start=asdict(state.session_start), week_start=asdict(state.week_start))
            if not state.latched:
                state.session_start = mark
                state.baseline_session = session
                if week != state.baseline_week:
                    state.week_start = mark
                    state.baseline_week = week
            after = dict(session=state.baseline_session, week=state.baseline_week,
                         session_start=asdict(state.session_start), week_start=asdict(state.week_start))
            state.transitions.append(dict(id=f"transition-{len(state.transitions)}", at=bar.start.isoformat(),
                                          session=session, policy=ROLLOVER_POLICY,
                                          decision="blocked" if state.latched else "applied",
                                          reasons=list(state.latched), mark=asdict(mark),
                                          before=before, after=after,
                                          assessed_before=risk["assessment"],
                                          valuation_event_id=events[-1]["id"]))
            risk, fx_time, fx = value(bar.start, bar.open)
        if active:
            if bar.open <= active["stop"] or bar.open >= active["target"]:
                price, reason = bracket_exit(bar, active["stop"], active["target"], slip)
                sell(bar.start, price, reason)
            elif risk["blocked"]:
                sell(bar.start, bar.open - slip, "risk_halt")
            risk, fx_time, fx = value(bar.start, bar.open)
        # One complete minute of latency after signal availability: never fill
        # at the same instant the signal-producing bar becomes available.
        while cursor < len(signals) and signals[cursor]["at"] < bar.start:
            signal = signals[cursor]
            cursor += 1
            before = attempts
            attempts += 1
            if bar.open <= signal["stop"] or bar.open + slip >= signal["target"]:
                decision = dict(eligible=False, reasons=["gap_invalidates_bracket"])
            else:
                proposal = dict(symbol=symbol, quantity=signal["quantity"], entry=bar.open,
                                stop=signal["stop"], entry_fee_usd=entry_fee, exit_fee_usd=exit_fee,
                                slippage_usd_per_share=slip, usd_to_gbp=fx,
                                quote_at=bar.start.isoformat(), fx_at=fx_time.isoformat())
                decision = check_entry(book, risk, proposal, bar.start.isoformat(), before)
            trace.append(dict(type="entry_check", signal=signal["id"], at=bar.start.isoformat(),
                              attempts=attempts, **decision))
            if decision["eligible"]:
                emit("buy", bar.start, symbol=symbol, quantity=signal["quantity"],
                     price=bar.open + slip, fee_usd=entry_fee, usd_to_gbp=fx)
                active = signal
                trace.append(dict(type="entry", signal=signal["id"], at=bar.start.isoformat(),
                                  quantity=signal["quantity"], price=bar.open + slip))
                risk, fx_time, fx = value(bar.start, bar.open)
        if active:
            outcome = bracket_exit(bar, active["stop"], active["target"], slip)
            if outcome:
                price, reason = outcome
                # OHLC does not reveal an intraminute execution time. Attribute
                # intrabar outcomes only when the completed bar is available.
                sell(bar.available_at, price, reason)
            elif index == len(bars) - 1:
                reason = "noon_flatten" if bar.available_at.astimezone(zone).time() == time(12) else "end_of_data"
                sell(bar.available_at, bar.close - slip, reason)
        final_risk, _, _ = value(bar.available_at, bar.close)
    for signal in signals[cursor:]:
        trace.append(dict(type="expired_signal", signal=signal["id"], reason="no_later_entry_bar"))
    return dict(mode="offline_scenario_simulation_only", live_trading_enabled=False,
                calendar_id=CALENDAR_ID,
                settlement_calendar_id=SETTLEMENT_CALENDAR_ID, settles_on=due.isoformat(),
                symbol=symbol, session=session, bars=len(bars), attempts=attempts,
                truncated_session=bars[-1].available_at.astimezone(zone).time() != time(12),
                halt_reasons=list(state.latched), blocked_reasons=final_risk["blocked_reasons"],
                baseline_session=state.baseline_session, baseline_week=state.baseline_week,
                session_start=asdict(state.session_start), week_start=asdict(state.week_start),
                assessment=final_risk["assessment"],
                final_ledger=book.last_report, trace=trace, ledger_events=events)
