# Delivery task register

Updated 10 October 2026. The [master plan](project-plan.md) defines scope,
dependencies and owner gates; this register turns its 64 tasks into an operational
queue. It does not relax a gate or replace the plan. Update a row when evidence,
readiness or ownership changes, and link the completing PR or private evidence from
[project status](project-status.md).

## How to use the register

Statuses are the five values defined by the plan: **not started**, **in progress**,
**blocked**, **complete** and **deferred**. Readiness uses:

- **ready** — independent work can start with existing authority and inputs;
- **conditional** — useful work can start, but the named dependency limits completion;
- **blocked** — no honest completion is possible until the named input or decision;
- **later** — predecessor phases or evidence should finish first.

Model assignments are starting points, not automatic routing. They follow current
[OpenAI model-selection guidance](https://learn.chatgpt.com/docs/models): Luna for
clear repeatable work, Sol for ordinary engineering and research that needs
judgment, and Astra for the hardest multi-step decisions. Use the lowest reasoning
effort that meets the acceptance evidence.

| Route | Use | Escalate when |
| --- | --- | --- |
| Luna low/medium | Hashes, inventories, deterministic command runs, narrow documentation and structured extraction | The contract is unclear, evidence conflicts, or code/financial semantics must change |
| Sol medium/high | Focused implementation, sourced research, tests, runbooks and coordinated repository changes | Accounting, risk or uncertain-order behavior is ambiguous; two materially different attempts fail; evidence changes the architecture |
| Astra medium/high | Architecture, financial/execution invariants, incident policy, experiment design and phase-gate review | Keep Astra; narrow an agreed implementation back to Sol after the contract is frozen |

Every PR still needs a separate final-diff review, meaningful validation and hosted
CI on the reviewed commit. A stronger model does not substitute for those controls.
Self-review remains self-review. Model/provider spending for the future trading
agent is a separate P6.4 owner gate; this development-routing table does not approve
paid services or change the project's £10 monthly external-cost ceiling.

## Ready queue

This is the ordered queue for work that can progress now. Take one focused PR at a
time unless the owner explicitly authorises parallel work.

| Order | Work package | Tasks | Start model | Completion evidence |
| ---: | --- | --- | --- | --- |
| 1 | Integrated protection faults and lifecycle rehearsal | P4.5 G | Sol high, Astra review | Map all X01–X24 to store/writer integration tests; restart, concurrency, cancellation/fill faults and full numeric lifecycle |
| 2 | Produce dated broker/entity capability matrix | P2.1–P2.2 | Sol medium/high | Primary-source matrix with exact UK entity/account/API facts and explicit unknowns; no account action |
| 3 | Build dated cost feasibility model | P2.4 | Sol high | Sourced fees/spread/FX/recurring costs compared with £3 trade risk and £10 monthly ceiling |

The bounded Massive access check is recorded in [PR #28](https://github.com/derekrivers/trad3r/pull/28);
original FX identity recovery and registered historical reproduction remain
conditional on the original files. P2.3/P3.1 qualification work remains open.
P4.1's contract, P4.2 atomic synthetic admission, P4.3's fenced synthetic writer
and P4.4 synthetic reconciliation are implemented. P4.5 prerequisite review found
empty-account and reservation-ownership defects, fixed in
[PR #34](https://github.com/derekrivers/trad3r/pull/34). Remaining lifecycle vectors
belong to protection and connected-paper phases. See [current evidence](project-status.md).

The [P4.5 protection contract](order-protection.md) and 24 acceptance specifications
are defined in [PR #35](https://github.com/derekrivers/trad3r/pull/35). Packages A–G
are sequential subdivisions of P4.5, not new master-plan tasks. Package A's pure
evaluator is implemented in [PR #36](https://github.com/derekrivers/trad3r/pull/36)
with 20 deterministic tests. Package B is implemented in
[PR #37](https://github.com/derekrivers/trad3r/pull/37) with 19 focused tests and
Astra review fixes for retained-input replay, freshness and identity blocking;
package C is delivered in [PR #38](https://github.com/derekrivers/trad3r/pull/38) with 19 focused tests and critical review fixes. Package D is delivered in [PR #39](https://github.com/derekrivers/trad3r/pull/39) with 12 focused tests and critical review fixes. Package E is delivered in [PR #40](https://github.com/derekrivers/trad3r/pull/40) with 14 focused tests for marker-first reducing-limit and protective-stop dispatch. Package F in [PR #41](https://github.com/derekrivers/trad3r/pull/41) adds [durable controls and synthetic owner recovery](order-controls.md) with 19 focused tests.
Package G covers integrated faults. Return
to Astra for changed financial/identity semantics and critical final-diff review.
The scenarios are specifications until executable implementation evidence is linked.

P0.3 and the off-host portion of P1.6 remain owner-input blockers. They do not block
the independent queue above. P5 connected paper submissions and all P10 activity
remain behind their explicit owner gates.

## Phase 0 — Adopt and verify

| ID | Status | Readiness / dependency | Start model | Deliverable and acceptance evidence |
| --- | --- | --- | --- | --- |
| P0.1 | complete | done | Luna low | Workspace, branch, remote, HEAD and hosted checks recorded without overwriting work; PR #24 |
| P0.2 | complete | done | Sol medium | Exact master plan adopted; README, roadmap, status and decisions linked; PR #24 |
| P0.3 | blocked | full design v2 has not been transferred | Astra medium | Import exact artifact, map every requirement to task IDs and record conflicts in capital, limits, model authority and discretionary scope |
| P0.4 | complete | done | Luna medium | Isolated VPS environment; 236 tests and 17 control checks passed with versions/hashes recorded |
| P0.5 | complete | ongoing inventory maintenance | Luna medium | Private inventory recorded; original stock archive and replay hashes verified; missing FX/experiment files remain explicit |

## Phase 1 — Recoverable offline research service

| ID | Status | Readiness / dependency | Start model | Deliverable and acceptance evidence |
| --- | --- | --- | --- | --- |
| P1.1 | complete | done | Sol medium | Root-owned pinned build, separate venv and unprivileged service user verified on ATLAS |
| P1.2 | complete | historical staging conditional on original files | Sol medium | Synthetic job staged with private immutable inputs and exact installed-code registration |
| P1.3 | complete | done | Sol high | Effective network denial, write boundaries, identity and cgroup limits passed 16 host checks |
| P1.4 | in progress | conditional on original FX, assumptions and registrations | Luna medium | Synthetic run/inspection/repeat complete; reproduce registered historical job without recomputation or substitution |
| P1.5 | complete | done for offline job | Sol high | Eight installed-build fault/recovery tests cover termination, publication interruption, competition and corruption |
| P1.6 | in progress | blocked for full exit by owner-selected off-host destination | Sol medium | Local locked backup inventory and separate restore pass; add recurring backup, retention, disk/log monitoring and off-host restore evidence |

## Phase 2 — Broker and data feasibility

| ID | Status | Readiness / dependency | Start model | Deliverable and acceptance evidence |
| --- | --- | --- | --- | --- |
| P2.1 | not started | ready for research; owner facts later | Sol medium | Dated primary-source matrix for exact UK entities, account types, paper prerequisites, APIs and authentication |
| P2.2 | not started | conditional on shortlisted broker/account facts | Sol high | Instrument, order, cash, settlement, partial-fill, commission and restart-query capability record with unknowns |
| P2.3 | in progress | bounded stock and GBP/USD requests now authenticated; terms and forward/decision-time evidence remain open | Luna medium | Verify entitled historical/forward stocks, quotes and FX; timestamps, limits, retention and permitted external-model use; separate corrected history from decision-time data |
| P2.4 | not started | conditional on P2.1–P2.3 evidence | Sol high | Sourced intended-quantity cost model including minimums, spread/slippage, FX and recurring project costs |
| P2.5 | not started | blocked by P2.1–P2.4 and owner selection | Astra medium | Decision record for broker/feed, session, universe, availability and proceed/revise/stop recommendation |

## Phase 3 — Qualified data and registered research

| ID | Status | Readiness / dependency | Start model | Deliverable and acceptance evidence |
| --- | --- | --- | --- | --- |
| P3.1 | in progress | one private 20-session stock/FX archive acquired and structurally audited; broader history and original identity remain open | Luna medium | Broader permitted stock/FX archives with provenance, hashes, inventory and acquisition timestamps; retain inspected sample role |
| P3.2 | in progress | conditional on P3.1 datasets | Sol high | Quality report covers order/duplicates/gaps, corporate actions, scale, independent prices, sessions, early closes, DST and FX |
| P3.3 | not started | ready for contract work; feed evidence later | Astra medium | Reviewed forward-feed contract for event/receipt time, completion, lateness, staleness, reconnects, corrections and spread evidence |
| P3.4 | not started | conditional on inventory and economic criteria owner review | Astra high | Preregister chronological partitions, hypotheses, search budget, universe, costs, metrics and pass/fail/inconclusive rules before outcomes |
| P3.5 | in progress | blocked for qualification by P3.1–P3.4; engineering runs retained | Sol high | Frozen baseline and same-cash comparison across registered periods with continuity, costs, settlement, halts and rejection/exposure/FX reporting |
| P3.6 | not started | later; required before dates beyond 2026 | Sol medium | Sourced calendar/settlement extension with deterministic tests; unsupported dates continue to fail closed |

## Phase 4 — Durable execution and account controls

| ID | Status | Readiness / dependency | Start model | Deliverable and acceptance evidence |
| --- | --- | --- | --- | --- |
| P4.1 | complete | [contract defined](order-lifecycle.md); runtime implementation belongs to P4.2–P4.5 | Astra medium | State/transition tables, stable identity rules, invalid transitions, late evidence and unknown-outcome handling; 14 synthetic acceptance specifications |
| P4.2 | complete | [atomic synthetic admission](order-admission.md); no adapter/dispatch | Sol high, Astra review | One transaction binds intent/attempt/versions/expiry and reserves cash/exposure/loss; duplicate, conflict, concurrency, restart, rollback and corruption tests |
| P4.3 | complete | [fenced synthetic writer](order-writer.md); no broker/network endpoint | Sol high, Astra review | Single writer and durable queue; marker precedes adapter call; lost acknowledgement becomes unknown; ownership epochs, rollback and no-retry faults tested |
| P4.4 | complete | [synthetic reconciliation](order-reconciliation.md); account-safety follow-up #34; connected adapter remains P5 | Sol high, Astra review | Synthetic cumulative entry reconciliation, including empty-account cash/settlement checks, mark/halts and reservation ownership; full independent inbox-to-account replay remains outside this delivered slice |
| P4.5 | in progress | [design and vectors defined](order-protection.md); packages A–F complete; G next | Astra high for control/recovery semantics; Sol high for bounded integration | Package F persists pause/objectives/incidents and evidence-bound synthetic owner recovery; package G integrated acceptance is next |
| P4.6 | not started | proposal ready after durable account schema; implementation requires owner review | Astra high | Persistent daily/weekly transition and restart proposal preserves all history/halts; implement only approved policy |
| P4.7 | not started | grows with P4.1–P4.6 | Sol high | Fault-injection suite for death, timeout, stale approval, concurrency, storage, duplicates and missing broker state; invariants survive restart |

## Phase 5 — Deterministic paper application

| ID | Status | Readiness / dependency | Start model | Deliverable and acceptance evidence |
| --- | --- | --- | --- | --- |
| P5.1 | not started | later; P2 decision, P4 controls and verified paper access | Sol high, Astra review | Paper-only neutral adapter verifies actual paper environment; no live endpoint/configuration path |
| P5.2 | not started | later; P2/P3 feed qualification and P4 | Sol high | Qualified feed/session/account snapshot; stale or unknown state blocks entry while exposure management remains available |
| P5.3 | not started | later; P5.1–P5.2 | Sol high, Astra review | Deterministic opportunity passes reservation, submission, protection, fills, cancellation, settlement and reconciliation |
| P5.4 | not started | later; P4/P5 state surfaces | Sol medium | CLI health/account/intent/halt/incident/report operations plus controlled start, pause, stop and recovery |
| P5.5 | not started | later; owner alert route | Sol high | Authenticated alerts and independent broker exposure route; escalation and availability documented without secrets |
| P5.6 | not started | later; P5.1–P5.5 and owner paper permission | Sol high, Astra review | Restricted separate paper service with protected credentials/config/logs/backups; offline sandbox preserved |
| P5.7 | not started | later; deployed paper service | Sol high, Astra review | Rehearse start, stale feed, disconnect, protection rejection, open-position restart, close and reconciliation; retain discrepancies |

## Phase 6 — Discretionary shadow agent

| ID | Status | Readiness / dependency | Start model | Deliverable and acceptance evidence |
| --- | --- | --- | --- | --- |
| P6.1 | not started | conditional; recorded-fixture design can follow P4 priorities | Sol high | Separate operational facts, append-only evidence and versioned narrative memory with cited evidence and timestamps |
| P6.2 | not started | conditional on P6.1 contracts | Sol high, Astra review | Schemas for thesis, uncertainty, proposal, conditional plan, invalidation, expiry and no-action; malformed output archived |
| P6.3 | not started | later; P6.1–P6.2 | Sol high | Bounded scheduled/event reviews with deduplication and exact model/prompt/settings/input/output records |
| P6.4 | not started | blocked by measured task needs and owner expenditure approval | Sol medium, Astra gate review | Provider/model/call budget decision; usage/cost tracking and hard stop on new calls at budget exhaustion |
| P6.5 | not started | later; P6.3 | Sol medium | Shadow proposals linked to opportunities/outcomes with expiry, age, invalidation, latency and disagreement metrics; ledger untouched |
| P6.6 | not started | later; P6.1–P6.5 | Sol high, Astra review | Adversarial/failure tests for poisoned evidence, time errors, stale context, provider/schema failures; model cannot alter controls |
| P6.7 | not started | later; stable shadow loop | Sol high | Reflections stored only as offline proposals; permitted adaptation frozen and every prompt/model/policy change versions the candidate |

## Phase 7 — Controlled discretionary paper experiment

| ID | Status | Readiness / dependency | Start model | Deliverable and acceptance evidence |
| --- | --- | --- | --- | --- |
| P7.1 | not started | later; P5/P6 and owner protocol approval | Astra high | Registered discretionary hypothesis, universe, information, constraints, prompts/model, revision rules and controls |
| P7.2 | not started | later; P7.1 | Sol high, Astra review | Valid proposals reach fresh deterministic checks; triggers remain within bound price/time/account/reserved capacity |
| P7.3 | not started | later; P7.1–P7.2 | Sol high, Astra review | Deterministic protection/exits and bounded agent exit authority specified and tested |
| P7.4 | not started | later; connected paper loop | Sol high | Measure observation-to-ack p50/p95/p99 and price movement; expired approvals rejected |
| P7.5 | not started | later; registered controls | Sol high | Comparable isolated control portfolios retain proposals, abstentions, invalidations, rejects, overrides and interventions |
| P7.6 | not started | later; completed experiment | Astra high | Review evidence, costs, discrepancies and workload; changed policy becomes a new experiment with preserved history |

## Phase 8 — Component evaluation and optional classifier

| ID | Status | Readiness / dependency | Start model | Deliverable and acceptance evidence |
| --- | --- | --- | --- | --- |
| P8.1 | not started | later; fixed opportunity stream and P7 evidence | Astra high | Preregister equal-constraint baseline/trader/judge/both comparisons with separate accounts and skipped opportunities |
| P8.2 | not started | later; discretionary evidence | Astra high | Compare discretionary portfolio with suitable fixed controls without false paired-trade claims |
| P8.3 | not started | later; only if comparison warrants judge | Sol high, Astra review | Judge has evidence-quality role, ABSTAIN/ERROR and at most one defined revision; hard vetoes stay in code |
| P8.4 | not started | later; P8.1–P8.3 | Sol high | Net contribution after execution/model costs, opportunity cost, drawdown, calibration, latency and uncertainty |
| P8.5 | deferred | optional; only if evidence justifies classifier | Astra high | Separate imitation/economic targets; rejected proposals lack realised labels and modelled counterfactuals are explicit |
| P8.6 | deferred | only if P8.5 proceeds | Sol high, Astra review | Chronological purged splits, training-only preprocessing and held-out shadow comparison against conditional monitoring |

## Phase 9 — Frozen forward evaluation

| ID | Status | Readiness / dependency | Start model | Deliverable and acceptance evidence |
| --- | --- | --- | --- | --- |
| P9.1 | not started | later; selected stable candidate | Astra high | Freeze code/config/policy/contracts/assumptions and preregister dates, sample floor, benchmarks, stress and decision rules |
| P9.2 | not started | later; P9.1 | Sol high | Forward trial with daily reconciliation, incidents/interventions, account continuity, model cost and owner time |
| P9.3 | not started | later; P9.2 evidence | Sol high | Account/project results include exposure, rejections, drawdown, slippage, latency, failures, contribution and uncertainty |
| P9.4 | not started | later; complete P9 evidence | Astra high | Separate operational/economic gate review and explicit proceed/extend/return/omit/stop decision with exact version |

## Phase 10 — Optional limited live pilot

| ID | Status | Readiness / dependency | Start model | Deliverable and acceptance evidence |
| --- | --- | --- | --- | --- |
| P10.1 | not started | blocked until P9 passes and owner chooses live review | Sol high, Astra gate review | Reverify permissions, costs/data rights, cash/settlement, owner availability, runbook and relevant tax/reporting requirements |
| P10.2 | not started | blocked by P10.1 and owner direction | Astra high | Separate live credentials/configuration, startup reconciliation and explicit activation; ordinary switching from paper impossible |
| P10.3 | not started | explicit owner gate | Astra high | Present exact candidate/account/funding/exposure/risk/incidents/evidence and record approval before activation |
| P10.4 | not started | only after authorised activation | Sol high, Astra gate review | Compare real costs/fills/stops/recovery with assumptions; stop or reduce when discrepancies invalidate case |
| P10.5 | not started | only during authorised operation | Sol high, Astra gate reviews | Daily reconciliation/backups, weekly operations, monthly cost/economic review, change revalidation and retirement plan |

## Register maintenance

On completion, update the task row, [project status](project-status.md), relevant
contract/runbook and decision record in the same focused PR. Record the reviewed
head SHA, tests, hosted CI, scope limits and next task. For a blocked row, state the
exact missing input and continue with the highest ready independent task. Never mark
an owner gate complete from inference, and never use model escalation to weaken a
financial limit or broaden authority.
