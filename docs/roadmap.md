# Delivery roadmap

This repository holds implementation and engineering acceptance notes. The owner's
existing project charter and research records retain financial decisions; this
initial engineering snapshot does not declare unresolved planning gates complete.

| Phase | Scope | Current state |
| --- | --- | --- |
| 0 | Charter and risk policy | Agreed for planning |
| 1 | Broker and data economics | Conditional IBKR candidate; account-specific checks open |
| 2 | Offline CLI foundation | Replay, offline ledger and durable risk observations |
| 3 | Data pipeline | First private sample structurally checked; broader validation open |
| 4 | One baseline strategy | Not started |
| 5 | Independent strategy validation | Not started |
| 6 | Optional classifier | Not started; begin in shadow mode |
| 7 | Broker execution and recovery | Not started |
| 8 | Forward paper trial | Not started |
| 9 | Restricted live review | Disabled; separate decision required |

The offline foundation can proceed using the accepted sample without funding a
brokerage account. It does not waive the full Phase 1 broker feasibility gate.

## Next implementation increment

1. Delivered: Decimal cash/position ledger, realised/unrealised P&L, GBP/USD cash,
   supplied FX, fees and explicit settlement dates. Verified calendar calculation
   and market-data freshness remain open.
2. Delivered: single-symbol/session fill scenarios with delayed entries, explicit
   costs, opening gaps, stop-first ambiguity, risk exits and noon/end-of-data
   flattening. Multi-symbol event batches and multi-session execution remain open.
3. Delivered: persistent initial baselines, loss latches and audit observations,
   with restart/concurrency/rollback tests. Period rollover stays blocked; a reviewed
   transition workflow and atomic order/ledger persistence remain open.
4. Delivered: pure entry diagnostics for quantity, exposure, settled cash and the
   £3 all-in trade budget. Persistent order/attempt reservations remain open.
5. Introduce one frozen strategy hypothesis and report net results only after those
   accounting and execution semantics are verified.

No broker credentials or news-classification service are needed for this increment.
Jev is a later optional classifier; its confidence is not a probability of profit.

## Next PR-sized backlog

- Delivered: order-entry diagnostics integrated into the isolated scenario simulator.
- Verified multi-symbol completed-bar batches and stronger quote/liquidity contracts.
- Verified session/settlement calendar and fresh price/FX observation contracts.
- Owner-reviewed period transitions that cannot clear an overall loss halt.
- Only then: one frozen baseline strategy and chronological evaluation reports.

The broker account is not needed for those offline tasks. No profitability or
live-readiness claim follows from the accounting example or passing unit tests.
