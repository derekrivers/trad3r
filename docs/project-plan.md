Version 1.0 · 10 October 2026 · Owner Derek · Delivery environment ATLAS VPS

Trad3r is a personal trading research project whose product goal is a discretionary agent that forms, records and revises trading theses during a market session. The agent proposes actions and conditional plans; deterministic code owns account truth, risk limits, order execution and recovery. The project must measure whether those decisions add value after all costs.

The immediate objective is to turn the existing offline research code into a reproducible VPS research environment, then build and evaluate a narrowly scoped paper application. A live pilot is an optional later decision. An honest negative research result is a valid outcome.

This is the consolidated delivery baseline for Derek and the Codex agent working in the trad3r project. It preserves agreed financial limits, distinguishes delivered capabilities from proposed work, and defines the evidence required to advance. Creating this document does not launch implementation, a service, a paid subscription or trading.

## Document authority and maintenance

This Page is the review source until Derek supplies it to the VPS agent. During Phase 0, import this version into the repository at `docs/project-plan.md` through the normal pull-request workflow. Once adopted and merged, that version-controlled file becomes the operational source of truth; this Page and downloadable copy are snapshots identified by version and date. Do not maintain two independently changing master plans.

Use explicit owner decisions to resolve scope and financial policy. Follow `AGENTS.md` for repository work. This plan defines delivery order; component contracts define implemented behaviour. If those sources conflict, record the conflict and resolve the affected requirement before implementing it. Do not infer relaxed risk limits from a newer design example.

Maintain a short status record at `docs/project-status.md` and decisions at `docs/decisions.md`. These are proposed paths to create in Phase 0. Each task records its ID, status, dependency, PR or commit, validation evidence, remaining limitation and next action. Valid statuses are not started, in progress, blocked, complete and deferred. An existing implementation receives credit after inspection; do not rebuild it merely because a phase lists the capability.

The phase numbers below replace the old plan's sequencing upon adoption. Old phase references remain historical. Preserve the original charter, experiment registrations and results rather than rewriting their meaning.

## Verified starting position

| Area | Position on 10 October 2026 |
| - | - |
| Repository | [derekrivers/trad3r](https://github.com/derekrivers/trad3r), reviewed revision `ea44cc8ec78703cc3310107e65cfc80739adb46a` |
| VPS workspace | Codex project trad3r on ATLAS VPS, checkout `/root/trad3r`; clean at the reviewed revision |
| Runtime deployment | No Trad3r systemd service found during inspection; a cloned checkout is not a deployed research service |
| Host prerequisites | Ubuntu 24.04, Python 3.12, virtual-environment support, timezone data and synchronised time; two CPUs, about 3.7 GiB RAM and 9.7 GB free disk at inspection |
| Engineering | CLI, deterministic replay, Decimal accounting, GBP/USD cash, settlement model, persistent risk observations and halts, conservative simulation, frozen baseline, registered experiments, verified result bundles and recoverable jobs |
| Data | Recorded private sample: AAPL, MSFT and F, 20 sessions, 23,400 raw regular-session minute observations, with historical FX proxies |
| Historical result | Three registered AAPL cost cases; eight candidates rejected by the £3 trade-risk cap in each case; zero trades |
| Performance interpretation | £8.49 account gain came from changing GBP valuation of USD cash; contribution above the same-cash reference was zero |
| Validation | Local check on 10 October: 236 tests completed, one skipped, suite successful; 17 control-rehearsal checks passed. Current reviewed main had passing hosted CI. These are not VPS test results |
| Missing capabilities | Connected broker/feed, durable order lifecycle, broker reconciliation, authorised persistent period transitions, discretionary agent, judge, classifier and forward paper trial |

The existing baseline `orb30-one-share-v1` is an engineering and comparison hypothesis, not the definition of the final discretionary product. No validated trading edge has been established.

The 9 October design discussion preserves discretionary theses, portfolio-level journalling and conditional plans. The full exported design v2 must be imported and reconciled in Phase 0; its exact text is not treated as verified by this document. This does not block checking or deploying the existing offline foundation.

Sources: [implementation roadmap](https://github.com/derekrivers/trad3r/blob/ea44cc8ec78703cc3310107e65cfc80739adb46a/docs/roadmap.md), [historical results](https://github.com/derekrivers/trad3r/blob/ea44cc8ec78703cc3310107e65cfc80739adb46a/docs/first-engineering-results.md), and [original phased plan](https://chatgpt.com/space/page_2a43c82f42e4819196ce18129dc1f552).

## Product scope and boundaries

The first connected application uses one broker, one verified paper account, a small fixed instrument universe and a documented session. It is long-only, cash-funded, without borrowing, shorting, derivatives or averaging down. Completed five-minute or fifteen-minute decision bars remain proposed defaults; acquisition and deterministic monitoring may use finer data when justified. The existing opening-range baseline has its own frozen minute-bar contract.

The product supports a portfolio journal, evidence-backed theses, explicit invalidation, conditional entry plans, expiry, position monitoring, deterministic protection, reconciliation and end-of-session reporting. A decision to make no trade is valid. Intended overnight exposure is zero; an unresolved position is an incident, not a successful flatten.

Evaluate two separate hypotheses: whether a bounded contextual filter improves a specified setup, and whether discretionary thesis formation improves portfolio outcomes within fixed constraints. The first is easier to diagnose. Its failure does not automatically disprove the second, and its success does not validate the second.

Defer a public product, other people's funds, multi-broker operation, distributed orchestration, a web dashboard, reinforcement learning, automatic strategy rewriting and high-frequency trading. A classifier and elaborate memory retrieval are optional later experiments. Use the existing Python CLI and simple durable storage unless a concrete requirement justifies more infrastructure.

## Financial policy and authority

| Policy | Agreed value or status |
| - | - |
| Eventual initial live funding | £1,000, following evidence gates and separate activation |
| Absolute cumulative account-loss trigger | £300 inclusive; initially £700 equity with no external flows |
| Planned all-in loss per trade | At most £3, including round-trip costs and conservative slippage |
| Session loss trigger | £10 inclusive, measured against the cash-flow-adjusted session baseline |
| Trading-week loss trigger | £25 inclusive, measured against the cash-flow-adjusted weekly baseline |
| Recurring external research costs | £10 per month; one-off purchases require separate review |
| Proposed connected-paper defaults | One simultaneous position, at most three entry attempts per session, maximum £500 open notional; confirm in the paper protocol |
| Loss budgets after restart | Preserve baselines and all latched halt reasons |
| Live activation and restart after a halt | Explicit owner decisions under the applicable policy |

Account P&L is current GBP net liquidation equity minus £1,000 minus subsequent external deposits plus withdrawals. Include unrealised losses, fees and FX effects. The £300 limit is absolute from the funding baseline, not trailing from peak equity. Also report peak-to-trough drawdown. Deposits, upgrades and process restarts must not erase losses.

Report account performance separately from project performance after externally paid data, hosting and model bills. Do not count a cost twice. Record both the treatment of the already-owned VPS and any incremental cash spending; do not silently assume hosting is free.

Daily and weekly durable-account transitions require a concrete owner-reviewed policy. The existing approved exception applies only to bounded isolated historical research with preserved account continuity and halts. It does not authorise timer-based resets for persistent paper or live accounts.

A halt blocks entries, cancels pending entries and manages remaining exposure under a tested incident procedure. Preserve effective protective orders while resolving exposure. Gaps, slippage and outages can exceed planned limits; an attempted close is not proof of being flat.

The development agent can carry out authorised reversible engineering, verification and repository work. Account opening/funding, paid services, connected order placement, live activation and changes to financial limits remain owner decisions. This plan is not blanket permission to execute those actions.

Sources: [agreed charter](https://chatgpt.com/space/page_a0f1eb50b6f88191b400cd8087e98481), [risk policy](https://github.com/derekrivers/trad3r/blob/ea44cc8ec78703cc3310107e65cfc80739adb46a/docs/risk-policy.md), and [engineering agreement](https://github.com/derekrivers/trad3r/blob/ea44cc8ec78703cc3310107e65cfc80739adb46a/AGENTS.md).

## Application architecture

| Component | Responsibility and boundary |
| - | - |
| Data acquisition and validation | Preserve licensed inputs, timestamps, provenance, calendar coverage, FX conventions and quality findings |
| Operational ledger | Authoritative cash, positions, fills, fees, settlement, order state, risk reservations and halt history |
| Evidence store | Append-only market observations, source references, received times, model inputs/outputs and decisions |
| Narrative memory | Versioned theses and reflections derived from evidence; never authoritative for fills, balances or policy |
| Trader agent | Produces structured proposals and conditional plans from permitted evidence |
| Judge | Optional separate assessment of evidence and setup quality; cannot override code vetoes |
| Risk and plan controller | Checks current account state, freshness, expiry, exposure, settled cash and risk; reserves capacity atomically |
| Order executor | Single writer with stable identities, durable submission state, broker reconciliation and protection |
| Reports and CLI | Shows actual state, blockers, exposure, costs, incidents, experiment versions and intervention needs |

Decision flow: validated observations → thesis or baseline candidate → structured plan → fresh deterministic checks and reservation → paper executor → reconciled ledger → report. Model output has no direct broker authority.

An approval binds the proposal, evidence snapshot, portfolio version, risk-policy version and expiry. Recheck at execution. Conditional plans contain trigger, entry bounds, size request, stop/exit policy, invalidation and expiry; code evaluates triggers and current risk. A completed bar does not by itself establish acceptable decision latency.

The model runtime must not hold broker credentials or write access to account truth, risk configuration or deployment controls. Treat news, filings and retrieved memory as untrusted input. Reflection may propose a new offline experiment; it cannot silently change tomorrow's trading policy.

## Phase map and dependencies

| Phase | Deliverable | Entry dependency |
| - | - | - |
| 0 | Adopted plan and verified VPS workspace | Existing checkout |
| 1 | Recoverable offline research service | Phase 0 |
| 2 | Broker and data capability decision | Phase 0; can proceed alongside offline engineering |
| 3 | Qualified datasets and registered research protocol | Phase 2 cost/data decisions for qualification; tooling can begin earlier |
| 4 | Durable order and account control layer | Phase 0; synthetic implementation need not wait for a broker |
| 5 | Complete deterministic paper loop | Phases 1, 2 and 4; qualified forward-feed subset of Phase 3 |
| 6 | Discretionary agent in shadow mode | Phase 3 evidence contracts and Phase 4 boundaries; recorded fixtures can start earlier |
| 7 | Controlled discretionary paper experiment | Phases 5 and 6, plus owner-approved paper protocol |
| 8 | Component comparisons and optional classifier | Phase 7 evidence; bounded filter comparisons may begin earlier |
| 9 | Frozen forward evaluation and decision | Selected configuration, stable operations and registered protocol |
| 10 | Optional limited live pilot and operation | Phase 9 gates and explicit owner authorisation |

These dependencies permit independent engineering work without authorising parallel agents or background jobs. Historical profitability is not required to prove operational paper integration, but an unsuccessful strategy must not be promoted as economically validated. Paper and live gates remain separate.

Legacy mapping: old charter Phase 0 is retained; old broker Phase 1 maps to new Phase 2; old foundation/data Phases 2–3 map mainly to new Phases 1 and 3; old strategy/validation Phases 4–5 map to new Phases 3, 8 and 9; old classifier Phase 6 maps to new Phase 8; old execution Phase 7 maps to new Phases 4–5; old forward trial Phase 8 maps to new Phases 7–9; old live Phase 9 maps to new Phase 10.

## Phase 0 Adopt the plan and verify the workspace

**Outcome:** the VPS agent has one versioned brief and can reproduce the current baseline. The repository clone and Codex project already exist.

| Task | Work and completion evidence |
| - | - |
| P0.1 | Inspect `/root/trad3r`, branch, remotes, working changes, `AGENTS.md`, current HEAD and hosted checks. Record findings without overwriting concurrent work |
| P0.2 | Adopt this plan through a documentation PR; add status and decision records; link README and roadmap to the canonical plan. Mark older validation notes with their historical scope |
| P0.3 | Import the full design v2 when available. Map its requirements to tasks and record any conflicts, especially paper capital, limits, model authority and discretionary scope |
| P0.4 | Create an isolated development environment and run the existing suite and control rehearsal on the VPS. Explain skipped tests and preserve evidence with code/environment versions |
| P0.5 | Inventory private source archives, FX exports, assumptions, registrations and results. Verify hashes against recorded evidence. Record missing assets explicitly without putting licensed content in git |

**Exit gate:** canonical plan adopted, clean and understood development state, successful VPS baseline verification, known private-data inventory and an ordered status file. Missing v2 or private inputs block only the dependent tasks; document and continue independent work.

**Next action:** P0.1 followed by the documentation adoption and VPS verification. Do not begin by changing the strategy or adding a broker SDK.

## Phase 1 Run offline research reliably on ATLAS

**Outcome:** an isolated, inspectable research job can complete and recover on the actual VPS.

| Task | Work and completion evidence |
| - | - |
| P1.1 | Separate development checkout from runtime. Install a pinned reviewed build under `/opt/trad3r` and a dedicated unprivileged `trad3r` account; keep code and environment unwritable by that account |
| P1.2 | Stage private jobs under `/var/lib/trad3r/jobs/JOB_ID`, with restrictive permissions and immutable source, assumptions and registration. Register using the exact installed code |
| P1.3 | Install and verify the existing oneshot service template. Test effective network denial, write boundaries and resource limits on the host, not merely template parsing |
| P1.4 | Run a synthetic fixture and then an explicitly registered historical job once its inputs are available. Inspect the result bundle; a repeat invocation must report completion without recomputing |
| P1.5 | Exercise termination before result publication, interruption after publication and competing runners. Preserve matching results and reject changed inputs or corrupted state |
| P1.6 | Implement private backup inventory and retention, disk/log monitoring, and restoration to a separate directory. Verify a restored completed job. Choose an approved off-host destination; local copies alone do not protect against host loss |

Start with the existing 1 GiB memory limit and 30-minute job timeout, then measure actual resource use before changing them. Preserve other ATLAS workloads. Keep code immutable for active registrations and retain prior builds needed to resume old jobs.

**Exit gate:** verified job, duplicate exclusion, host sandbox tests, recovery drill, backup restore and a usable runbook. A synthetic-only milestone may be reported if private history is unavailable; it is not a reproduced historical run.

**Boundary:** no daily paper timer or automatic rerun of old market data. Offline acquisition is a separate explicit step because the backtest service disables networking.

Source: [VPS operations contract](https://github.com/derekrivers/trad3r/blob/ea44cc8ec78703cc3310107e65cfc80739adb46a/docs/vps-operations.md).

## Phase 2 Establish broker and data feasibility

**Outcome:** one concrete account/feed combination with dated capability and cost evidence.

| Task | Work and completion evidence |
| - | - |
| P2.1 | Produce a dated broker matrix: exact UK entity, permissions, account type, paper prerequisites, supported API, authentication and reauthentication. IBKR remains a candidate; compare alternatives only where a requirement warrants it |
| P2.2 | Verify instrument IDs, quantity/tick rules, settlement, currency cash, protective orders, partial fills, cancel/replace behaviour, execution IDs, commission events and restart queries |
| P2.3 | Confirm entitled historical and forward stock/quote/FX data, timestamps, rate limits, retention and permitted use with external models. Distinguish corrected history from data available at decision time |
| P2.4 | Build a sourced cost model for intended quantities: entry/exit commissions, minimum charges, spreads, slippage, FX and recurring data/model/hosting bills. Compare against the £3 trade budget and £10 monthly ceiling |
| P2.5 | Record the broker/feed decision, exact session and initial instrument universe, owner availability, unresolved restrictions and a proceed/revise/stop recommendation |

The engineering cost cases were assumptions, not verified account fees. Diagnose why all existing candidates were rejected, separating stop distance, fees, FX and slippage. Do not widen the cap or silently tune the frozen hypothesis to create trades.

**Exit gate:** Derek selects the account/feed and any expenditure; the capability record establishes a feasible paper path or explains why scope must change. Missing account access does not prevent synthetic Phase 4 work.

**Owner involvement:** provide existing account/access facts through secure mechanisms; approve new account arrangements or spending separately. Never request secrets in chat or repository files.

## Phase 3 Qualify data and register the research

**Outcome:** experiments have credible inputs, fixed comparisons and an auditable evaluation protocol.

| Task | Work and completion evidence |
| - | - |
| P3.1 | Acquire permitted broader history and FX with exact provenance, source hashes, symbol/date inventory and acquisition timestamps; retain the 20 inspected sessions as engineering data |
| P3.2 | Check missing/duplicate/out-of-order records, corporate actions, price scale, independent price samples, regular sessions, early closes, timezone/DST boundaries and FX availability |
| P3.3 | Define forward-feed contracts for event time, receipt time, bar completion, lateness, staleness, reconnects and corrections. Add quote/spread evidence or explicitly conservative substitutes |
| P3.4 | Register chronological development, validation and untouched test periods; hypotheses, search budget, opportunity universe, baselines, costs, metrics and acceptance/uncertainty rules before viewing outcomes |
| P3.5 | Run the frozen baseline and same-cash comparison with account continuity, costs, settlement and preserved halts. Report rejections, blocked time, exposure and FX effects as well as trades |
| P3.6 | Extend exchange and settlement calendars beyond 2026 before using later dates, with sourced rules and tests; unsupported dates must continue to fail closed |

Use executed-price assumptions and adverse cost/latency/gap scenarios. Keep all attempted variants in an experiment register. Do not recycle inspected history as untouched evidence or randomly split minute rows across train/test partitions. Historical model evaluation must disclose possible knowledge of later events; prospective evidence is central for the discretionary agent.

**Exit gate:** reproducible input qualification report, registered protocol and inspected result bundles. Economic thresholds and sample-size rules must be concrete before the relevant evaluation starts; the agent must not invent convenient pass marks after results.

**Possible outcome:** the present strategy is infeasible under unchanged limits. Record that finding and register any new hypothesis separately.

## Phase 4 Build durable execution and account controls

**Outcome:** a synthetic adapter proves the application handles uncertain orders and persistent accounts correctly.

| Task | Work and completion evidence |
| - | - |
| P4.1 | Define durable intent and order states: proposed, reserved, submitting, unknown, acknowledged, partially filled, filled, cancel pending, cancelled and rejected. Model actual allowed transitions and retain stable client/broker identities |
| P4.2 | Atomically persist intent, attempt count and reserved risk/cash before submission. Bind authorisation to evidence, account and policy versions plus expiry. Concurrent approvals must not exceed shared limits |
| P4.3 | Implement a single order writer and durable submission queue. A lost acknowledgement requires reconciliation; never blindly retry a possibly accepted order. Add ownership locking now and stronger fencing if deployment requires multiple writers |
| P4.4 | Reconcile orders, executions, positions, currency cash, commissions and settlement at startup and after disconnect. Process duplicate and late events idempotently; unexplained differences block entries |
| P4.5 | Implement protection and incident states for pause, halt, unresolved exposure and verified flat. Handle partial fills, stop rejection, cancel/fill races, manual intervention and simultaneous exit requests |
| P4.6 | Propose persistent daily/weekly transition and reviewed restart procedures. Preserve overall loss history and every latched halt; implement only the approved policy |
| P4.7 | Add fault-injection tests for process death, timeout, stale approval, concurrent entry, storage failure, duplicate events and missing broker state. Assert ledger/risk invariants across restart |

**Exit gate:** synthetic end-to-end intent, execution and reconciliation; no duplicate orders under tested faults; risk reservations and attempt counts survive restart; disarmed startup and unresolved-state blocking are demonstrated. No live endpoint is introduced.

The existing risk diagnostic is reused but does not become an order authorisation merely by being called. Extend the contracts explicitly and test the boundary.

## Phase 5 Complete the deterministic paper application

**Outcome:** one setup operates through verified paper execution with accurate reporting and recovery.

| Task | Work and completion evidence |
| - | - |
| P5.1 | Build one paper-only broker adapter behind the neutral interface. Verify the account/environment from supported broker evidence; a port number or user-supplied label alone is insufficient |
| P5.2 | Integrate the qualified forward feed, session clock and account snapshot. Block entries on stale/missing data, unknown account state or unsupported dates; retain an independent exposure-management path |
| P5.3 | Run the deterministic opportunity generator through reservation, submission, protection, fills, cancellation, settlement and reconciliation using the same core contracts exercised offline |
| P5.4 | Provide CLI operations to inspect health, account state, outstanding intents, halt reasons, incidents and reports; add controlled start, pause, stop and reviewed recovery actions |
| P5.5 | Add authenticated operational alerts and a separate owner route to inspect/close exposure through the broker. Define escalation and availability without embedding notification secrets |
| P5.6 | Deploy a separate paper service with necessary restricted network access, protected credentials, versioned configuration, logs and backups. Keep the offline sandbox intact |
| P5.7 | Rehearse start, stale feed, broker disconnect, rejected protection, restart with an open position, end-of-session closure and reconciliation. Record every discrepancy |

Constrain the simulated research allocation to £1,000 even if the broker's paper balance is larger. Reconcile the allocation consistently; do not grant extra buying power from the broker's default demo funds.

**Exit gate:** an operational engineering paper trial with reconciled orders, cash and positions; retained halt history; tested incidents and acceptable owner workload. Performance during debugging is engineering evidence, not the final evaluation.

**Owner gate:** verified paper access and explicit authorisation for connected paper submissions. The repo's existing development authority alone does not authorise placing orders.

## Phase 6 Add discretionary intelligence in shadow mode

**Outcome:** the agent produces inspectable, bounded decisions without influencing orders.

| Task | Work and completion evidence |
| - | - |
| P6.1 | Implement separate operational facts, append-only evidence and versioned narrative memory. Every thesis cites available evidence and has creation/update times |
| P6.2 | Define schemas for thesis, uncertainty, proposal, conditional plan, invalidation, expiry and no-action decision. Reject malformed or unsupported outputs and archive the rejection |
| P6.3 | Implement portfolio-level scheduled and event-driven review, with deduplication, call limits and bounded context. Record exact model identifier, prompts, settings, input hashes and outputs |
| P6.4 | Choose model/provider using the task, measured latency, permitted data use and the agreed cost envelope. Track token/call usage and total cost; stop new model requests when the configured budget is exhausted |
| P6.5 | Log proposals alongside deterministic opportunities and later observable outcomes. Measure proposal expiry, evidence age, invalidation, decision latency and disagreement without changing the trading ledger |
| P6.6 | Test poisoned news/memory, missing evidence, future timestamps, stale portfolio context, provider errors, refusals and schema failures. The model cannot change risk policy, credentials or operational facts |
| P6.7 | Record reflections as proposals for offline evaluation. Freeze the permitted adaptation policy; changes to model, prompt or policy create a new candidate version |

**Exit gate:** a bounded shadow run with traceable evidence, reliable schemas, observed cost and latency distributions, safe failure behaviour and zero model authority over orders.

**Model failure behaviour:** prevent new agent-originated entries while deterministic protection and reconciliation continue. Do not use a blanket HOLD response as incident handling for an open position.

## Phase 7 Run a controlled discretionary paper experiment

**Outcome:** agent planning is exercised through the same deterministic controller as the baseline.

| Task | Work and completion evidence |
| - | - |
| P7.1 | Register the discretionary hypothesis, universe, information access, portfolio constraints, prompts, model version, allowed thesis revision and comparison accounts before the run |
| P7.2 | Connect valid proposals to fresh code checks. Conditional triggers act only within approved price/time bounds, current account state and remaining reserved capacity |
| P7.3 | Enforce deterministic protection and exits as defined by the experiment. Specify which exit proposals the agent may make and how code validates them |
| P7.4 | Measure end-to-end p50/p95/p99 latency and price movement from observation through decision to acknowledgement; reject expired plans rather than executing stale approvals |
| P7.5 | Maintain comparable separate simulated portfolios for controls and record all proposals, abstentions, invalidations, rejects, overrides and human interventions |
| P7.6 | Review evidence quality, costs, discrepancies and intervention load. Any changed policy creates a new experiment; preserve the prior account/result history |

**Exit gate:** a completed engineering paper experiment that answers whether the discretionary loop is operationally usable and yields interpretable comparison data. Profitability is evaluated under the registered criteria, not inferred from an attractive trading narrative.

**Owner gate:** approve the connected-paper protocol and specific permissions. A failed contextual-filter experiment does not mechanically forbid a separately justified discretionary experiment.

## Phase 8 Evaluate components and optional acceleration

**Outcome:** retain components only when evidence supports their contribution.

| Task | Work and completion evidence |
| - | - |
| P8.1 | For a fixed deterministic opportunity stream, preregister comparisons: baseline alone, baseline with trader filter, baseline with judge filter, and baseline with both. Use equal constraints and separate accounts; preserve skipped opportunities |
| P8.2 | Evaluate the discretionary strategy separately against appropriate fixed controls. It may generate different opportunities, so compare portfolio outcomes without falsely treating them as identical trade pairs |
| P8.3 | Implement the optional judge with separate code vetoes and evidence-quality assessment. Include ABSTAIN and ERROR; permit at most one defined evidence-backed revision rather than repeated persuasion |
| P8.4 | Measure net contribution after execution and model costs, rejection opportunity cost, drawdown, calibration where meaningful, latency and uncertainty. Record null and negative findings |
| P8.5 | Only if justified, train a classifier with distinct imitation and economic-outcome targets. Rejected proposals have no realised trade outcome; mark any counterfactual labels as modelled |
| P8.6 | Use chronological splits, purging where label horizons overlap, training-only preprocessing and held-out evaluation. Start any classifier in shadow mode and compare against conditional-plan monitoring as an alternative |

**Exit gate:** a recorded retain, revise, shadow-only or omit decision for each component. The classifier is optional; it cannot block completion of the core application. Neither a judge score nor classifier confidence can override a hard limit.

Promoting a component changes the strategy version and requires the relevant independent/forward validation again.

## Phase 9 Freeze the system and evaluate forward performance

**Outcome:** an explicit research decision based on new evidence and stable operations.

| Task | Work and completion evidence |
| - | - |
| P9.1 | Freeze code, strategy, model/prompt configuration, risk policy, input contracts and execution assumptions. Register trial dates, opportunity/sample requirements, benchmarks, cost stress and pass/fail/inconclusive rules |
| P9.2 | Run the forward paper trial with daily reconciliation, retained incidents and interventions, account continuity, model expenditure and owner-time logs |
| P9.3 | Produce account and total-project results, exposure, rejected/expired opportunities, drawdown, slippage, latency, failure rates, component contribution and uncertainty |
| P9.4 | Review operational and economic gates independently. Record proceed to owner review, extend evidence, return to a named phase, omit a component, or stop the experiment |

The earlier plan proposed a minimum of eight trading weeks and 50 completed trades, with both required as an initial evidence floor. Retain these as provisional inputs to protocol design, not proof of statistical adequacy or permission to force trades. Sparse activity or correlated observations can require longer. Approve the final requirements before starting the qualifying trial.

**Operational gate:** no unresolved critical accounting/execution defect; proven restart/reconciliation and exposure protection; reliable reports, alerts and acceptable owner workload.

**Economic gate:** meet the preregistered net and total-cost criteria against the controls, with adequate uncertainty analysis and stress evidence. A positive headline balance or paper fill quality alone is insufficient.

**Exit gate:** a signed-off review decision with limitations and exact candidate version. Passing paper evidence permits consideration of live trading; it does not activate it.

## Phase 10 Optional live pilot and continuing operation

**Outcome:** if separately authorised, a small live execution study and a sustainable operating routine.

| Task | Work and completion evidence |
| - | - |
| P10.1 | Reverify account permissions, current fees/data rights, actual cash/settlement rules, owner availability and the complete live runbook. Resolve any relevant tax/reporting requirements |
| P10.2 | Prepare a separate live configuration and credentials boundary, startup reconciliation and explicit activation procedure. Keep accidental paper-to-live switching impossible under ordinary settings |
| P10.3 | Present Derek with the exact candidate, account, funding, initial exposure cap, risk policy, incident/restart controls and evidence. Record explicit approval before activation |
| P10.4 | Compare actual commissions, spreads, fills, stop behaviour and recovery with paper assumptions. Stop or reduce scope when discrepancies invalidate the research case |
| P10.5 | Maintain daily reconciliation and backups, weekly operational review, monthly cost/economic review and revalidation after material changes. Document safe retirement and evidence retention |

The earlier plan proposed £100, £250 and £500 maximum open-notional stages while retaining the £1,000 initial funding baseline. These are review proposals, not activated permissions. Each increase requires a separate decision; calendar time or winning trades never increase exposure automatically. The earlier two-week/20-trade review floor is an operational proposal, not proof of edge.

When a halt occurs, preserve the loss history and effective protection, resolve exposure and require the applicable owner review. Broker closure, programme restart, software upgrade and withdrawal of cash do not erase the experiment record.

**Exit decision:** continue within approved limits, hold, reduce exposure, return to paper research or retire. There is no fixed live launch date or promised income.

## Decisions and external dependencies

| Decision | Owner and timing | Work that can continue meanwhile |
| - | - | - |
| Supply and reconcile full design v2 | Derek provides artifact; agent maps it in Phase 0 | Offline verification and deployment preparation |
| Locate private history and result bundles | Derek/agent inventory in Phase 0 | Synthetic tests and service drills |
| Choose broker/account and forward feed | Derek, informed by Phase 2 evidence | Neutral execution and recorded-data work |
| Approve paid data/model services or budget change | Derek before purchase/use beyond existing authority | Cost model and local fixtures |
| Define persistent period transitions and restart permissions | Derek reviews Phase 4 proposal before connected use | Historical exception remains limited to its existing scope |
| Confirm session, universe, exposure and attempt defaults | Derek approves first paper protocol | Capability tests and configurable implementation |
| Select model and call budget | Agent prepares evidence; Derek approves expenditure and experiment | Schema, evidence and mocked-provider tests |
| Set numeric economic and uncertainty criteria | Derek reviews protocol before qualification outcomes | Data qualification and engineering runs |
| Choose off-host backup and alert destinations | Derek supplies destination/access preferences | Local restore exercises and notification stubs |
| Enable connected paper or eventual live orders | Derek authorises the specific stage | All preceding reversible preparation |

Record a blocked task with the exact missing input and next independent task. Do not treat an external dependency as permission to fabricate data, change a limit or mark a gate complete.

## Quality and release rules

Each implementation task should fit a focused feature-branch PR. Preserve concurrent work, avoid direct commits to main, review the final diff separately and fix findings. Record the reviewed head SHA, meaningful test evidence and scope limits. Hosted CI must pass on that same head before an authorised merge, using an expected-head check. Self-review must be described accurately.

Test financial invariants and failure boundaries rather than reproducing implementation details. Retain deterministic synthetic fixtures and exclude secrets/licensed data from CI and public git. Reuse and extend the existing suite; do not rerun unrelated expensive experiments without a reason.

A completed task has working behaviour, appropriate validation, updated contracts/runbook, a PR/commit reference and a status entry. A completed phase additionally has its exit evidence and any required owner decision. A green test suite does not establish profitability, broker capability or deployment isolation.

Store public code, schemas and synthetic fixtures in git. Keep licensed inputs, private result bundles and credentials in their approved private locations. Backups must preserve database consistency, registrations, code references and checksums. Never delete a risk database or overwrite results to make a failure disappear.

Deploy pinned reviewed builds. An incomplete registered job needs its matching code; preserve the prior installation and original result semantics. Restart paper services disarmed and reconcile before enabling entries. Define rollback for code and schema changes without rolling back the account's economic history.

End each work session with completed work, validation, unresolved risks/dependencies and the next task. Do not imply that a paused chat continues working or that this document schedules unattended runs.

## First VPS work package and handoff

The first package is Phase 0 plus the synthetic portion of Phase 1. It should produce the adopted plan, verified VPS test results, a private-data inventory, an isolated offline runtime, a verified synthetic job and recovery/restore evidence. Follow with a registered historical reproduction once the retained inputs are located.

Use this handoff after reviewing the plan and deciding to start that package:

> Work in the existing trad3r project at /root/trad3r on ATLAS VPS. Read AGENTS.md, this plan, README and the current component contracts. Inspect repository state and preserve concurrent changes. Adopt this document as docs/project-plan.md through a focused PR and add the status and decision records. Complete Phase 0 and the authorised offline Phase 1 work, beginning with VPS baseline verification and a synthetic job. Reuse existing implementations. Record exact revision, tests, recovery evidence, private-data availability and remaining blockers. Follow the repository review and hosted-CI requirements. Keep broker submissions, live mode, paid purchases and financial policy changes behind their recorded owner gates. Continue independent engineering when a task lacks external inputs, and finish with a concrete next backlog.

This handoff is prepared for Derek to submit; it has not been sent to another chat. Later packages should name the next phase, approved dependencies and any new authority explicitly.

## Supporting records

- [Original phased project plan](https://chatgpt.com/space/page_2a43c82f42e4819196ce18129dc1f552)

- [Agreed charter and risk policy](https://chatgpt.com/space/page_a0f1eb50b6f88191b400cd8087e98481)

- [Broker feasibility research](https://chatgpt.com/space/page_69ec178972dc8191a2aabe3d647feb65)

- [Repository](https://github.com/derekrivers/trad3r)

- [Research readiness](https://github.com/derekrivers/trad3r/blob/ea44cc8ec78703cc3310107e65cfc80739adb46a/docs/research-readiness.md)

- [Paper readiness and existing engineering backlog](https://github.com/derekrivers/trad3r/blob/ea44cc8ec78703cc3310107e65cfc80739adb46a/docs/paper-readiness.md)

- [Frozen baseline contract](https://github.com/derekrivers/trad3r/blob/ea44cc8ec78703cc3310107e65cfc80739adb46a/docs/strategy.md)

Version 1.0 consolidates the verified 10 October starting position, retained financial decisions, discretionary-agent direction and proposed implementation phases. Task statuses must be updated from subsequent evidence; this snapshot does not claim later work is complete.
