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
| 4 | One baseline strategy | Frozen continuous-account runner; qualification gates open |
| 5 | Independent strategy validation | Not started |
| 6 | Optional classifier | Not started; begin in shadow mode |
| 7 | Broker execution and recovery | Not started |
| 8 | Forward paper trial | Not started |
| 9 | Restricted live review | Disabled; separate decision required |

The offline foundation can proceed using the accepted sample without funding a
brokerage account. It does not waive the full Phase 1 broker feasibility gate.

## Next implementation increment

1. Delivered: Decimal cash/position ledger, realised/unrealised P&L, GBP/USD cash,
   supplied FX, fees and validated scheduled 2026 T+1 settlement dates. Research
   cash release waits until after the settlement day in New York. Real broker
   reconciliation and market-data freshness remain open.
2. Delivered: single-symbol/session fill scenarios with delayed entries, explicit
   costs, opening gaps, stop-first ambiguity, risk exits and noon/end-of-data
   flattening. Multi-session accounting scenarios now carry cash, settlement and
   latches. Ordinary series keep their period block; a separately approved bounded
   research path supports eligible rollover. Multi-symbol execution remains open.
3. Delivered: persistent initial baselines, loss latches and audit observations,
   with full-history consistency replay and restart/concurrency/rollback tests.
   Period rollover stays blocked; a reviewed
   transition workflow and atomic order/ledger persistence remain open.
4. Delivered: pure entry diagnostics for quantity, exposure, settled cash and the
   £3 all-in trade budget. Persistent order/attempt reservations remain open.
5. Delivered: frozen one-share opening-range hypothesis, isolated scenarios and
   bounded continuous-account replay with approved rollover. Qualified strategy
   evaluation remains blocked on research inputs and registered validation periods.

No broker credentials or news-classification service are needed for this increment.
Jev is a later optional classifier; its confidence is not a probability of profit.

## Next PR-sized backlog

- Delivered: order-entry diagnostics integrated into the isolated scenario simulator.
- Delivered: scheduled minute-grid coverage diagnostics, optional strict replay
  and atomic multi-symbol completed-bar batches. Quote/liquidity contracts and
  simultaneous multi-symbol execution remain open.
- Delivered: bounded, sourced 2026 exchange session calendar; holidays, early
  closes and unsupported years checked in data, entry diagnostics and simulation.
- Delivered: separate scheduled 2026 T+1 settlement calendar and explicit research
  cash-release policy, including bank holidays on which equities still trade.
- Broker cash reconciliation, broader historical calendar coverage, unscheduled
  closure handling and fresh price/FX observation contracts.
- Delivered: owner-approved bounded isolated research rollover, with full account
  continuity and no clearing of any halt. Durable/paper/live rollover stays absent.
- Delivered: causal completed-minute feature snapshots with explicit warmup and
  frozen opening ranges. No learned model, labels or strategy selection yet.
- Delivered: `orb30-one-share-v1` candidate generator and single-session integration
  with unchanged risk checks. No profitability claim, tuning or classifier.
- Delivered: explicit-window research inventory, recorded engineering sample audit,
  evaluation protocol structure and a concrete owner-reviewable period proposal.
- Delivered: continuous frozen-baseline integration and a synthetic walkthrough.
- Delivered: account-level evaluation summaries, observed equity curves and a
  same-cash no-trade reference. Qualified evaluation still needs history/FX/cost
  evidence, preregistered partitions and predeclared acceptance/stress criteria.
  See [research dependencies and ordered continuation](research-readiness.md).
- Delivered: dry-run-first local Massive stock/FX acquisition with bounded requests,
  secure local credentials, pacing, provenance hashes and exclusive archive output.
- Delivered: causal FX archive-to-scenario preparation with explicit fixed-cost
  assumptions and exact archive binding.
- Delivered: connected Massive FX export/import, complete modelled FX coverage for
  the engineering sample, and explicit millisecond acquisition bounds after checking
  actual endpoint behavior. Next: broader history, independent data checks, qualified
  economic assumptions and registered chronological evaluation.

The broker account is not needed for those offline tasks. No profitability or
live-readiness claim follows from the accounting example or passing unit tests.
