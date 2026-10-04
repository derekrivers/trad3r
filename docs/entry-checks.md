# Offline entry diagnostics

`entry-check` reconstructs the supplied ledger event file and reads an existing
risk database without modifying either. Their valuation timestamps, GBP equity
and cumulative external flows must agree. The proposal's FX must match the ledger
valuation. A missing valuation or inconsistent inputs is an error, never approval.

Using the risk-state walkthrough **before** recording its synthetic loss:

```sh
python -m trad3r entry-check runs/risk.sqlite examples/ledger.json examples/entry.json --at 2026-09-04T14:02:00Z --attempts 0
```

All proposal fields are mandatory; see `examples/entry.json`. Prices, FX and costs
are supplied scenario assumptions. There is no market-data connection. Valuation,
price and FX timestamps must be no later than the decision and at most 60 seconds
old. A matching timestamp does not authenticate an observation or its provenance.

The first version permits only flat-to-long, whole-share USD stock entries. It
checks the existing risk block, New York session date, 10:00–11:29:59 entry
window, no current position (including the same symbol), and fewer than three
previous entry attempts. The [bounded 2026 calendar](calendar.md) rejects scheduled
closed days and errors outside its supported year. Early-close mornings retain
the same entry window. Every result identifies the calendar version.

With q shares, one-way adverse execution allowance s, GBP-per-USD fx, entry price
e, stop p, and explicit entry/exit USD fees:

- Planned loss = q × ((e + s) − (p − s)) × fx + both fees × fx.
- Exposure = q × (e + s) × fx, capped at GBP 500.
- Settled USD requirement = q × (e + s) + both fees. Including the exit fee is a
  conservative reserve; the diagnostic does not actually lock that cash.
- Planned loss may equal, but not exceed, GBP 3 or the remaining overall, daily
  and weekly loss headroom. Equality can consume the remaining budget and trigger
  the corresponding halt on the next observation.

The allowance must cover the chosen spread/slippage scenario; it is not a measured
spread or a guarantee. Gaps, latency and currency movement can exceed planned loss.

Malformed proposals exit 2. Valid but rejected proposals return exit 0 with
`eligible: false` and reasons. `eligible: true` is only a diagnostic result. The
caller supplies the number of previous attempts, including rejected attempts;
repeated checks do not reserve cash, increment that number or authorise an order.
Atomic live order admission and persisted attempt counts are not implemented.
The offline simulator will own its attempts and recheck at the simulated fill.

All responses explicitly disable live trading. This command is never an exit gate:
a risk block must not prevent reducing or closing an existing position.
