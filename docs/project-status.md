# Project status

Updated 10 October 2026. [Master plan](project-plan.md) version 1.0 is canonical,
adopted in [PR #24](https://github.com/derekrivers/trad3r/pull/24), merge
`413075d227a407b4be7a2b372ca77a7edb0c3b14`.
[Decisions](decisions.md) retain owner gates. Runtime remains pinned to reviewed
`ea44cc8ec78703cc3310107e65cfc80739adb46a`; documentation has advanced separately.
The [task register](task-register.md) assigns readiness, acceptance evidence and a
cost-conscious starting model to all 64 master-plan tasks.

## Active package

| Task | Status | Dependency | PR / revision and validation | Remaining limitation / next action |
| --- | --- | --- | --- | --- |
| P0.1 workspace | complete | Existing checkout | #24; clean main at `ea44cc8`, matching origin and hosted CI recorded in [baseline](vps-baseline-2026-10-10.md) | Preserve branch isolation |
| P0.2 plan adoption | complete | P0.1 | #24; supplied bytes preserved; self-review and hosted CI passed on `0f596df` before expected-head merge | Update status as evidence changes |
| P0.3 design v2 | blocked | Owner artifact | #24 / D002; owner confirms no transfer yet | Transfer actual design; map requirements/conflicts |
| P0.4 VPS baseline | complete | P0.1 | #24 / `ea44cc8`; 236 tests, no skips; 17 control checks | Baseline establishes engineering controls only |
| P0.5 private inventory | complete | P0.1 | `8ebda1a`; [original stock intake](stock-sample-intake-2026-10-10.md) matches source/replay hashes; strict validation and full-window audit pass; [Massive FX intake](massive-fx-intake-2026-10-10.md) records a separate private archive | Original stock sample remains authoritative; original combined FX archive/export, assumptions, registrations and results still missing |
| P1.1 pinned runtime | complete | P0 adoption | `ea44cc8`; [deployment record](vps-deployment-2026-10-10.md); unprivileged user, root-owned release and venv | Preserve build for registered jobs |
| P1.2 stage job | complete | P1.1 | `ea44cc8`; AAA synthetic job registered before execution; protected inputs | Original stock sample received; historical FX and experiment files still missing |
| P1.3 host sandbox | complete | P1.1–2 | `ea44cc8`; all 16 actual host probe checks passed | No power-loss or OOM-exhaustion guarantee |
| P1.4 execute job | in progress | P1.3 | `ea44cc8`; synthetic job completed, inspected and repeat returned already_complete; new Massive archive structurally audited | Synthetic portion complete; original stock replay reproduced; registered historical reproduction awaits original FX/experiment files and qualification |
| P1.5 recovery | complete | P1.4 synthetic | `ea44cc8`; eight installed-package recovery tests passed inside sandbox | Offline job faults only; no broker reconciliation claim |
| P1.6 backups | in progress | P1.4 synthetic | `ea44cc8`; five-file checksum inventory and separate restore returned already_complete; disk/log checks recorded | Select off-host destination, recurring backup/monitoring and bounded retention; local copies insufficient |
| P2.1 broker matrix | complete | Public primary-source research | [PR #43](https://github.com/derekrivers/trad3r/pull/43); [dated IBKR/Saxo matrix](broker-capability-matrix.md); primary sources checked on 10 October | Public matrix only; actual permissions and account access remain G01/G02 |
| P2.2 capabilities | in progress | Selected account and authorised observations | [PR #43](https://github.com/derekrivers/trad3r/pull/43); [execution/account gap record](broker-capability-matrix.md#p22--execution-and-account-evidence) with closure evidence | G01–G06 remain unverified, including Gateway overnight history, correction/fee mapping and settled cash |
| P2.3 feed evidence | in progress | Exact selected account/feed and rights | Bounded Massive stock/FX access and current public feed-price screening | Forward quotes, decision-time delivery, retention/model rights and selected broker API entitlements remain unverified |
| P2.4 costs | complete | Public conditional research | [PR #44](https://github.com/derekrivers/trad3r/pull/44); [dated cost model](cost-feasibility.md); broker fees, FX, spread/slippage formula and recurring stack compared with caps | Per-trade cases remain conditional; no complete recurring stack is evidenced under £10/month; account tariffs/invoices remain P2.2/P2.3 inputs |
| P2.5 broker/feed decision | in progress | P2.2/P2.3 evidence and remaining owner fields | Owner selected IBKR and subsequently reported that the account was created and approved on 10 October 2026 | Verify exact entity/account type, permissions and costs, then record feed, session, universe, availability and proceed/revise/stop; no account access, funding or paid access is authorised to the agent |
| P4.1 order contract | complete | Independent synthetic design | [PR #29](https://github.com/derekrivers/trad3r/pull/29); [order lifecycle v1](order-lifecycle.md); reviewed transition/identity contract and 14 synthetic acceptance specifications | Definition complete; implementation credit is tracked separately in P4.2–P4.5 |
| P4.2 atomic admission | complete | P4.1 contract | [PR #30](https://github.com/derekrivers/trad3r/pull/30); [atomic admission](order-admission.md); deterministic duplicate/conflict/concurrency/restart/rollback tests | Synthetic flat-account reservations only; no writer, adapter, fills, cancellation or migration of the existing risk/ledger history |
| P4.3 single writer | complete | P4.1–P4.2 | [PR #31](https://github.com/derekrivers/trad3r/pull/31); [fenced synthetic writer](order-writer.md); durable marker and projection replay; deterministic ownership, lost-acknowledgement, restart and commit-failure tests | Synthetic adapter only; P4.4 now resolves supplied evidence; version-1 stores require explicit writer migration |
| P4.4 reconciliation | complete | P4.1–P4.3 | [PR #32](https://github.com/derekrivers/trad3r/pull/32); [synthetic reconciliation](order-reconciliation.md); cumulative evidence, atomic account adjustments and replay; deterministic partial-fill, late-fee, disconnect, rollback and corruption tests | Synthetic USD entry evidence only; pending/sell settlement, cancellation and protection belong to P4.5; version-1/2 stores require explicit migration |
| P4.5 protection | complete | P4.1–P4.4 | [PR #35](https://github.com/derekrivers/trad3r/pull/35) contract; [PR #36](https://github.com/derekrivers/trad3r/pull/36) package A; [PR #37](https://github.com/derekrivers/trad3r/pull/37) package B; [PR #38](https://github.com/derekrivers/trad3r/pull/38) package C; [PR #39](https://github.com/derekrivers/trad3r/pull/39) package D; [PR #40](https://github.com/derekrivers/trad3r/pull/40) package E with 14 deterministic tests; [PR #41](https://github.com/derekrivers/trad3r/pull/41) package F with 19 focused tests for durable controls and evidence-bound synthetic owner recovery; [PR #42](https://github.com/derekrivers/trad3r/pull/42) package G with 14 integrated rehearsals and two cancellation handoff fixes | A–G delivered; [integrated acceptance](order-protection-acceptance.md) maps X01–X24, including process death and the numeric lifecycle. Owner recovery has no production authentication or halt/budget reset |

P4.5 prerequisite review produced [PR #34](https://github.com/derekrivers/trad3r/pull/34):
empty-order snapshots now check cash/settlement and persist marks/halts; older
order evidence cannot release a newer reservation or resurrect an unsent expiry.
Eight added regression tests cover these boundaries, late-exposure incidents,
rollback and reservation replay. This is P4.4 hardening; P4.5 now has a defined
implementation contract. Full independent reconstruction from inbox evidence
remains a v3 scope limit and is required for the new v4 implementation.

P0's permitted exit is met: missing design/private inputs block only dependent
work. The original stock sample and replay hashes are now verified. Other missing
assets are explicitly recorded and their hashes remain unverified. The **synthetic
P1 milestone** is verified; P1's full exit gate remains open for the recorded backup
and historical dependencies.

## Ordered continuation

1. Transfer design v2, the original combined stock/FX archive (or original FX
   export), assumptions, registrations and result bundles. A separate Massive
   stock/FX archive is now retained for structural inspection, but the original
   stock sample remains authoritative; match remaining identities before
   registered historical reproduction (P0.3/P1.4).
2. Owner selects an off-host backup destination/access route. Finish restore from
   that destination, recurring backup/monitoring and retention (P1.6).
3. Close P2.2/P2.3 account, quote/data and recurring-invoice evidence using the
   delivered [broker matrix](broker-capability-matrix.md) and
   [conditional cost model](cost-feasibility.md). G01–G06 remain explicit.
4. Complete P2.5 after the recorded IBKR intent: feed, session, universe,
   availability and proceed/revise/stop remain open;
   then P3.1–P3.6 qualification and P4.6–P4.7 controls. No cross-day settlement
   release precedes P4.6; no existing v3 account migrates without a separate reviewed migration. Per-task status is maintained
   in the register; existing offline work keeps its credit in the roadmap.
5. P5–P10 remain not started in the canonical dependency order. No AI/classifier
   integration precedes the accounting/execution controls.

The operational order and model-routing rules are maintained in the
[ready queue](task-register.md#ready-queue). Keep this short status page focused on
current evidence; update both records when task readiness or completion changes.

Connected paper submissions, live execution, purchases and financial-policy
changes remain gated. The offline units are inactive after successful explicit
runs. No unattended work or daily service timer is scheduled.
