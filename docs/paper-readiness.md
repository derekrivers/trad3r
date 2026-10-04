# Control rehearsals and forward paper readiness

Historical engineering backtesting has started. Actual broker paper trading has
not started: there is no broker account, connected paper adapter or qualified
forward feed. The current code has no order endpoint. Passing this drill does not
enable one or establish a profitable trading strategy.

## Run the synthetic control drill

From the reviewed repository, choose a new directory beneath existing `runs/`:

```sh
python -m trad3r rehearse-controls runs/controls-01
python -m trad3r risk-status runs/controls-01/synthetic-risk.sqlite
python -m trad3r risk-history runs/controls-01/synthetic-risk.sqlite
python -m trad3r ledger runs/controls-01/synthetic-ledger-events.json
```

The drill has 17 assertions. It starts one explicitly synthetic £1,000 account,
converts £400 into a hypothetical $500 at a fixed rate, and checks a coherent entry
diagnostic. It then checks the £3 trade cap, £500 exposure cap, settled cash, three
attempt limit, stale/future quotes, stale FX and stale account marks. These are
diagnostics: no orders, fills or persistent attempt reservations are generated.

A deliberately unrealistic cash FX shock takes equity to exactly £700, triggering
daily, weekly and overall halts. Reopening the database must retain them. Restoring
equity to £1,000 must not clear them or admit a fresh entry. The next synthetic day
must retain those halts and add `period_review_required`, with the original period
baselines untouched. Finally the journal and risk history must reconcile.

The new directory contains `synthetic-risk.sqlite`, `synthetic-ledger-events.json`
and `rehearsal-report.json`. The final report is published only after every assertion
passes. A failed/aborted drill may leave partial evidence; preserve it. Rerunning
against an existing directory fails instead of replacing/resetting it. A new drill
directory is a separate synthetic test fixture, never a way to resume an account
that has halted. Fixed September 2026 timestamps are test inputs, not current marks.

Exit code 0 means the drill completed. Its report still says `paper_ready=false`,
`broker_connected=false`, `generated_orders=0` and `live_trading_enabled=false`.
The test suite also reads the retained risk database in a fresh Python process,
and injects defective entry/retention behavior to prove the drill cannot publish a
success report when those checks fail.

## Gates before a forward paper pilot

| Gate | Current evidence | Work required |
| --- | --- | --- |
| Historical engineering execution | Three fixed AAPL cost cases, all eight candidates rejected per case | Broader preregistered feasibility study; sourced dated costs and independent data checks |
| Account-level control calculations | Synthetic and historical tests, persisted halts | Reconcile actual broker cash, equity, FX, positions and settlement conventions |
| Broker identity and permissions | No account configured; IBKR remains a conditional candidate | Owner establishes suitable account access; verify exact entity/account type, paper environment and supported API permissions |
| Forward data | Historical stock/FX proxies only | Qualify entitled timely quotes, FX and session state; detect stale, missing, out-of-order and disconnected data |
| Durable order lifecycle | Not implemented | Atomic intent/attempt reservation; stable client IDs; acknowledgements, rejects, partial fills, cancellations and commission events |
| Restart reconciliation | Offline risk and experiment jobs tested | Start disarmed; reconcile broker open orders, executions, positions and cash; resolve unknown outcomes before any new submission |
| Period transitions | Durable store blocks new dates | Separate owner-reviewed transition policy; no inherited historical-only rollover exception and no halt clearing |
| VPS operations | Offline service template and runbook | Confirm actual host, install pinned build, verify isolation, backups, time sync and recovery on that host |
| Pilot acceptance | No forward trial protocol yet | Preregister sessions, permitted behavior, discrepancy/failure criteria and reports before the pilot begins |

The official [IBKR paper API limitations](https://www.interactivebrokers.com/docs/tws-api/doc/notes-limitations/limitations/paper-trading)
explain that simulated execution can differ from live execution. Account setup and
entitlements must be verified for the actual account; a Massive market-data account
is not a broker paper account. No funding or subscription purchase is implied here.

## Ordered implementation backlog

1. Add a broker-neutral durable order-intent journal with fault-injected synthetic
   adapter tests. A submitted-but-unacknowledged intent must become an unresolved
   outcome requiring reconciliation, never an automatic duplicate order. Persist
   attempts before submission and retain them after rejection or restart.
2. Add broker snapshot/ledger reconciliation and disarmed startup checks. Cover
   duplicate/late executions, partial fills, cash/position drift and disconnects.
   Keep unexpected outcomes blocked; do not fabricate fills or discard differences.
3. Once account/API details are available, implement an explicit paper-only adapter
   and verify the environment. Do not trust a user-selected port or label alone as
   evidence that an account is paper. No live mode or live credentials path.
4. Qualify the actual feed and cost/cash contracts, then make the durable period
   transition proposal concrete for owner review. Historical approval is insufficient.
5. Preregister the forward pilot and rehearse start, intraday checks, flatten/cancel,
   disconnect, restart and end-of-day reconciliation on the actual paper service.

There is no requirement to train an AI model before these gates. A later classifier
must first run in shadow mode using causal inputs and chronological held-out tests,
with its decisions compared against the frozen baseline after costs. It must never
change risk limits, clear halts or substitute a confidence score for accounting or
execution evidence.
