# Delivery roadmap

The [canonical project plan](project-plan.md), version 1.0 dated 10 October 2026,
now defines phase numbering and dependencies. [Project status](project-status.md)
records current delivery evidence and the next work; [decisions](decisions.md)
records authority and unresolved inputs. The implementation inventory below is
retained as engineering history, not a second master plan.

| Phase | Deliverable | Current state |
| --- | --- | --- |
| 0 | Adopt plan and verify VPS | Adopted; VPS verified; design v2 not transferred |
| 1 | Recoverable offline research service | Synthetic host runtime/recovery/restore verified; off-host backup open |
| 2 | Broker and data capability decision | Account-specific evidence and owner decision open |
| 3 | Qualified datasets and protocol | Engineering sample/results exist; qualification open |
| 4 | Durable order and account controls | P4.1–P4.4 delivered; P4.5 packages A–F implemented; package G integrated faults and period transition pending |
| 5 | Deterministic paper application | Not started; connected submissions need owner approval |
| 6 | Discretionary shadow agent | Not started |
| 7 | Discretionary paper experiment | Not started; protocol and owner approval required |
| 8 | Comparisons and optional classifier | Not started |
| 9 | Frozen forward evaluation | Not started |
| 10 | Optional live pilot | Disabled; separate owner decision required |

Older phase references in preserved research records use the historical numbering;
the canonical plan provides the mapping. No historical experiment is reclassified
as untouched validation or a VPS run by adoption of this plan.

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
- Delivered: engineering experiment registration, exact-input/code checks,
  immutable result bundles and replay-based inspection.
- Delivered: all three predeclared historical engineering cost cases, with eight
  candidates each, all risk-rejected and no trades; zero contribution above cash.
  See [recorded results](first-engineering-results.md). No strategy qualification.
- Delivered: recoverable offline jobs, duplicate-run exclusion and a network-disabled
  systemd template with an operating/backup guide. [ATLAS synthetic deployment](vps-deployment-2026-10-10.md)
  now verifies host isolation, installed-build recovery and local restore; off-host
  backup and historical reproduction remain open.
- Delivered: executable synthetic control rehearsal, retained risk/journal evidence
  and [explicit forward paper gates](paper-readiness.md).
- Defined: [P4.1 durable order lifecycle](order-lifecycle.md), stable identities,
  allowed transitions, unknown-outcome rules and synthetic acceptance cases.
- Delivered: [P4.2 atomic synthetic admission](order-admission.md), including
  durable identities, attempts, version/expiry binding and cash/exposure/loss
  reservations with concurrency and rollback tests.
- Delivered: [P4.3 fenced synthetic writer](order-writer.md), including durable
  marker-before-call, ownership epochs, lost-acknowledgement blocking and explicit
  recovery without blind retry.
- Delivered: [P4.4 synthetic reconciliation](order-reconciliation.md), including
  startup/disconnect fencing, cumulative executions and commissions, atomic cash,
  position, reservation and risk-latch updates, and durable contradiction handling.
  [Account-safety follow-up #34](https://github.com/derekrivers/trad3r/pull/34) covers
  empty-order mark/settlement checks, newer-reservation ownership and unsent expiry
  tombstones; full independent inbox-to-account replay remains future hardening.
- Defined: [P4.5 protection contract](order-protection.md), 24 acceptance scenarios
  and seven bounded implementation packages. Integrated acceptance remains pending.
- Delivered: P4.5 package A pure protection/quantity/permission evaluator with
  deterministic X01–X05/X16 coverage and no persistence or dispatch surface.
- Delivered in [PR #37](https://github.com/derekrivers/trad3r/pull/37): P4.5 package B
  fresh-v4 shared sell-quantity and fee allocations, retained-input capacity replay,
  fresh evidence and incident blocking, with no migration or dispatch surface.
- Delivered in [PR #38](https://github.com/derekrivers/trad3r/pull/38): P4.5 package C cumulative buy/sell accounting,
  fee finality, retained contradictions and pending lots with no cash-release path.
- Delivered in [PR #39](https://github.com/derekrivers/trad3r/pull/39): package D
  fenced synthetic cancellation and evidence-only quantity release.
- Delivered in [PR #40](https://github.com/derekrivers/trad3r/pull/40): package E
  marker-first synthetic reducing-limit and protective-stop dispatch.
- Delivered: [package F durable protection controls](order-controls.md), including
  pause, desired action, latched incidents and evidence-bound synthetic owner recovery.
- Next: package G integrated restart, concurrency, fault and lifecycle rehearsal
  on Sol High, with Astra review of financial and recovery invariants.
  Close private-input and off-host
  backup dependencies independently and qualify forward data.
  Durable paper period transitions require a separate owner-reviewed policy.

The broker account is not needed for those offline tasks. No profitability or
live-readiness claim follows from the accounting example or passing unit tests.
