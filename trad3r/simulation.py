"""Single-session scenario execution, not a strategy or broker emulator."""
from bisect import bisect_right
from dataclasses import asdict
from datetime import date, time, timedelta
from zoneinfo import ZoneInfo

from .admission import check_entry
from .ledger import Ledger, nonnegative, positive, shares, utc
from .risk import Mark, Policy, assess


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


def simulate(bars, scenario):
    """Consume validated Bar objects for one symbol/session, with supplied signals.

    Every run is an isolated research account. No durable risk database is reset
    or touched, and results cannot authorise another research or live account.
    """
    symbol, session = scenario["symbol"], scenario["session"]
    zone = ZoneInfo("America/New_York")
    bars = list(bars)
    if not bars or any(b.symbol != symbol or b.session != session for b in bars):
        raise ValueError("Simulation requires exactly one symbol and session")
    if any(b.start != a.available_at for a, b in zip(bars, bars[1:])):
        raise ValueError("Simulation bars must be contiguous and chronological")
    bars = [b for b in bars if b.start.astimezone(zone).time() < time(12)]
    if not bars:
        raise ValueError("No bars before the noon flatten deadline")
    due = date.fromisoformat(scenario["settles_on"])
    if due.isoformat() != scenario["settles_on"] or due <= date.fromisoformat(session):
        raise ValueError("Supply an explicit future settlement date")
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
    book, events, trace = Ledger(), [], []
    latched, active, cursor, attempts = (), None, 0, 0

    def emit(kind, at, **fields):
        event = dict(id=f"sim-{len(events)}", type=kind, at=at.isoformat(), **fields)
        book.apply(event)
        events.append(event)

    def value(at, price):
        nonlocal latched
        fx_time, fx = fx_at(at)
        emit("value", at, usd_to_gbp=fx, prices={symbol: price} if book.position else {})
        report = book.last_report
        mark = Mark(report["equity_gbp"], report["deposits_gbp"], report["withdrawals_gbp"])
        assessment = assess(mark, Mark(Policy().initial_capital), Mark(Policy().initial_capital), latched)
        latched = assessment.halt_reasons
        risk = dict(mode="offline_risk_observations_only", live_trading_enabled=False,
                    as_of=report["as_of"], mark=asdict(mark), baseline_session=session,
                    assessment=asdict(assessment), blocked=bool(latched), blocked_reasons=list(latched))
        return risk, fx_time, fx

    def sell(at, price, reason):
        nonlocal active
        _, fx = fx_at(at)
        quantity = book.position.quantity
        emit("sell", at, symbol=symbol, quantity=quantity, price=positive(price),
             fee_usd=exit_fee, usd_to_gbp=fx, settles_on=scenario["settles_on"])
        trace.append(dict(type="exit", at=at.isoformat(), signal=active["id"],
                          price=price, quantity=quantity, reason=reason))
        active = None

    start = bars[0].start
    emit("fund", start, amount=Policy().initial_capital)
    emit("exchange", start, from_currency="GBP", **scenario["funding"])
    for index, bar in enumerate(bars):
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
        value(bar.available_at, bar.close)
    for signal in signals[cursor:]:
        trace.append(dict(type="expired_signal", signal=signal["id"], reason="no_later_entry_bar"))
    return dict(mode="offline_scenario_simulation_only", live_trading_enabled=False,
                symbol=symbol, session=session, bars=len(bars), attempts=attempts,
                truncated_session=bars[-1].available_at.astimezone(zone).time() != time(12),
                halt_reasons=list(latched), final_ledger=book.last_report, trace=trace, ledger_events=events)
