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
| Historical engineering execution | Three fixed AAPL cost cases, all eight candidates rejected per case; [P2.4 decomposition](cost-feasibility.md#diagnosis-of-the-eight-retained-rejections) records available headroom | Recover retained per-candidate traces; broader preregistered feasibility study and independent data checks |
| Account-level control calculations | Synthetic and historical tests, persisted halts | Reconcile actual broker cash, equity, FX, positions and settlement conventions |
| Broker identity and permissions | [IBKR/Saxo public matrix](broker-capability-matrix.md) delivered; no account configured | Close G01/G02: verify actual entity/permissions, account and supported paper identity/authentication |
| Forward data | Historical stock/FX proxies only | Qualify entitled timely quotes, FX and session state; detect stale, missing, out-of-order and disconnected data |
| Durable order lifecycle | P4.1 [contract](order-lifecycle.md), P4.2 [atomic admission](order-admission.md), P4.3 [fenced synthetic writer](order-writer.md) and P4.4 [synthetic reconciliation](order-reconciliation.md), plus P4.5 [integrated protection](order-protection-acceptance.md) delivered | Connected paper adapter and protection verification; durable settlement release remains P4.6 |
| Restart reconciliation | Synthetic startup/disconnect invalidation and complete cumulative snapshots tested | Close matrix G04/G05: cross-midnight history, execution corrections, final fees and cash; empty open orders do not resolve unknown submissions |
| Period transitions | Durable store blocks new dates | Separate owner-reviewed transition policy; no inherited historical-only rollover exception and no halt clearing |
| VPS operations | [ATLAS synthetic offline service](vps-deployment-2026-10-10.md): pinned build, isolation, time sync, recovery and local restore verified | Off-host backup and separate connected-paper deployment/incident verification remain open |
| Pilot acceptance | No forward trial protocol yet | Preregister sessions, permitted behavior, discrepancy/failure criteria and reports before the pilot begins |

The official [IBKR paper API limitations](https://www.interactivebrokers.com/docs/tws-api/doc/notes-limitations/limitations/paper-trading)
explain that simulated execution can differ from live execution. Account setup and
entitlements must be verified for the actual account; a Massive market-data account
is not a broker paper account. No funding or subscription purchase is implied here.

## Ordered implementation backlog

1. Close P2.2/P2.3 account/feed/invoice [broker matrix gaps](broker-capability-matrix.md)
   against the delivered [P2.4 cost screen](cost-feasibility.md), then obtain P2.5
   owner selection. P4.5 synthetic protection is delivered; its
   [X01–X24 acceptance evidence](order-protection-acceptance.md) still needs
   applicable connected-paper qualification.
2. Once account/API details are available, implement an explicit paper-only adapter
   and verify the environment. Do not trust a user-selected port or label alone as
   evidence that an account is paper. No live mode or live credentials path.
3. Qualify the actual feed and cost/cash contracts, then make the durable period
   transition proposal concrete for owner review. Historical approval is insufficient.
4. Preregister the forward pilot and rehearse start, intraday checks, flatten/cancel,
   disconnect, restart and end-of-day reconciliation on the actual paper service.

There is no requirement to train an AI model before these gates. A later classifier
must first run in shadow mode using causal inputs and chronological held-out tests,
with its decisions compared against the frozen baseline after costs. It must never
change risk limits, clear halts or substitute a confidence score for accounting or
execution evidence.
