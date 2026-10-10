# Durable order lifecycle contract

Contract `order-lifecycle-v1`, defined for P4.1 on 10 October 2026. P4.2
implements its [atomic synthetic admission](order-admission.md) subset and P4.3
implements the [fenced synthetic writer](order-writer.md). P4.4 implements
[synthetic reconciliation](order-reconciliation.md). No broker adapter exists. The
[P4.5 protection contract](order-protection.md) defines exposure controls and their
acceptance scenarios. Its package A pure evaluator is implemented; transactional
packages B–G remain pending. These components must be tested together before the
Phase 4 exit gate can pass.

## Authority and scope

Start with one synthetic account, whole-share USD equities, flat-to-long entries
and position-reducing sells. No borrowing, shorts, fractional shares, replacement
orders, broker-native brackets or concurrent independent entries in v1. Multiple
partial executions of one order are supported. A symbol alone is insufficient
instrument identity for a future adapter; bind its venue/currency-qualified
instrument identifier before any connected use.

Keep the existing £1,000 initial funding, £300 cumulative account-loss halt,
£10 session halt, £25 weekly halt and £3 planned all-in trade risk. Preserve the
existing £500 entry exposure cap and three entry attempts per session. No order
event resets an attempt count, budget baseline or halt. The isolated historical
rollover exception does not apply. A loss halt blocks entries but does not itself
prohibit a verified position-reducing action.

`check_entry` and `risk-status` remain diagnostics. An eligible diagnostic is not
a reservation or submission permission. The existing in-memory ledger and separate
risk SQLite store are not an atomic account/order system. Do not bolt an order
database onto them and claim multi-store atomicity.

## Identity and persisted records

Every record carries a schema version and immutable account/environment namespace.
V1 execution fixtures identify themselves as synthetic; a label does not establish
a broker environment. Paper/live adapters and account migration are separate work.

| Record / key | Required meaning |
| --- | --- |
| `intent_id` | Unique within the account, allocated and persisted before admission; bound to an immutable canonical proposal digest and producer candidate ID. Reusing either identity with changed economics is a conflict. |
| Proposal | Instrument, side, positive whole quantity, order type and any price bound, time-in-force, entry/exit purpose, evidence references, costs and FX assumptions. An entry also has a planned stop and all-in risk calculation; a planned stop does not assert broker protection. |
| `client_order_id` | Unique within account/environment, persisted before any dispatch and never reused, including after rejection, cancellation, restart or database restore. One intent creates at most one order in v1. |
| Broker identity | Nullable until known; immutable mapping from account/environment plus adapter-defined durable broker ID scope to `client_order_id`. Session-local handles are aliases, not durable identities. Contradictory or ambiguous mappings block entries. |
| Authorisation / reservation | Intent digest, policy version/digest, account/ledger/risk/evidence versions, quote/FX times, decision time, expiry, session, cash currency/amount, planned GBP loss and exposure. It is bound to one intent; never a reusable approval token. |
| Operation ID | Separate stable IDs for submission and cancellation. Persist command payload/digest and dispatch status; a cancel request never creates a new sell order. |
| Event ID | Producer-scoped unique ID plus canonical payload digest, intent/order references, source event time, local receipt time and local commit sequence. Commit sequence orders replay; source timestamps may arrive out of order. |
| Execution ID | Account/adapter-scoped durable execution identity, linked order, quantity, price, source time and currency. Duplicate delivery is not another fill. Fees have their own stable identities/revisions and execution linkage. |
| Order projection | State, version, original quantity, known executed quantity, last confirmed state, broker mapping, pending operation and unresolved reasons. Store the evidence from which the projection was derived. |

Quantities are positive whole shares (known executed quantity starts at zero).
Amounts use finite decimal strings and explicit currencies, never binary floats.
Accepted ordinary executions cannot exceed original quantity or change instrument,
side or account; contradictory evidence follows the incident rules below.

For broker identifiers that change across sessions, retain all verified aliases and
their scopes. Never match an unidentified execution solely by symbol, size or time.
A synthetic adapter must provide stable identities; a future adapter unable to
provide equivalent evidence is unsupported until its contract is reviewed.

Exact duplicate commands/events are idempotent: no additional attempts, fills,
fees, reservations or dispatches. Return the current projection and current block
status, not a cached approval. Same key with different payload records a conflict
and blocks entries. Different event IDs cannot bypass execution-ID deduplication.
Check exact durable duplicates before rejecting a stale expected version; this
allows a lost commit response to be recovered without repeating its effects.
Unknown-order executions remain durable unresolved evidence; never discard them
because their order record is missing.

## State meanings

Order state describes the remaining order, not whether the account is flat or its
cash settled. Execution quantity and reconciliation status are separate facts.

| State | Meaning |
| --- | --- |
| `proposed` | Persisted immutable intent; no reservation or dispatch permission. |
| `reserved` | Admission committed with attempt accounting and resources; no dispatch has started. |
| `submitting` | Dispatch marker committed before the adapter call. The marker does not prove whether the call occurred; recovery must treat acceptance as possible. |
| `unknown` | Submission, cancellation or continuing order status cannot be established. Preserve last confirmed state, fills, resources and unresolved operation. No submit retry is permitted. |
| `acknowledged` | Correlated evidence establishes acceptance and a working remainder, with zero known fills. |
| `partially_filled` | Positive known executions below ordered quantity and confirmed working remainder. |
| `filled` | Unique valid executions account for the entire ordered quantity. This says nothing about settlement, fees or a resulting open position. |
| `cancel_pending` | A cancellation command is durably queued/possibly sent; the remainder can still fill. Retain prior status and execution quantity. |
| `cancelled` | Local withdrawal provably preceded dispatch, or authoritative evidence establishes that no remainder can execute, including confirmed expiry. Any executed portion remains a position/account fact. |
| `rejected` | Local admission/dispatch rejection before submission, or definitive broker rejection of the original order with no executions. A rejected cancel request is not a rejected order. |

`filled`, `cancelled` and `rejected` are terminal for ordinary commands. They do
not erase pending reconciliation, fees, settlement or protection obligations.
Never use `ordered_quantity - known_executed_quantity` as a claim about working
quantity after cancellation or while status is unknown.

## Transition table

All rows require verified identity, schema, quantities, current version and event
deduplication. Evidence means a correlated synthetic adapter event initially; a
future broker adapter must establish its provenance and completeness. Every
unlisted command/state transition fails closed without dispatch or resource release.

| From | Trigger and required evidence | To / effect |
| --- | --- | --- |
| none | New unique valid proposal | `proposed` |
| `proposed` | Atomic admissible entry or verified reducing-exit admission | `reserved` |
| `proposed` | Evaluated admission denied | `rejected`, retained reason and attempt evidence |
| `proposed`, `reserved` | Local withdrawal/expiry, provably never dispatch-marked | `cancelled`; release only through the account transaction |
| `reserved` | Writer revalidates bound authority and commits dispatch marker | `submitting`; only then may adapter be called |
| `reserved` | Changed versions, fresh evidence and renewed admission before original expiry, never dispatch-marked | Stay `reserved`; atomically replace authorisation/reservation with audit, same intent economics and attempt slot |
| `reserved` | Revalidation fails before dispatch marker, other than expiry | `rejected`; retain entry attempt; atomically release unused reservation |
| `submitting` | Correlated accepted/working status with zero known executions | `acknowledged` |
| `submitting` | Definitive rejection of original submission, zero executions | `rejected`; release requires complete account evidence |
| `submitting`, `acknowledged`, `partially_filled`, `cancel_pending` | Timeout, restart or loss of status continuity leaves outcome unresolved | `unknown`; preserve fills, pending operation and resources |
| `acknowledged`, `partially_filled` | Persist a cancellation request for this order | `cancel_pending`; cancellation does not reduce risk by itself |
| `submitting`, `acknowledged`, `partially_filled` | Unique partial execution establishes acceptance and working remainder | `partially_filled`; atomically account for execution |
| `cancel_pending` | Unique partial execution | Stay `cancel_pending`; account for execution, retain cancellation obligation |
| Any dispatched nonterminal state | Unique executions reach original quantity | `filled`; a pending cancellation is now moot, but its later responses remain auditable |
| `acknowledged`, `partially_filled`, `cancel_pending`, `submitting` | Correlated definitive cancellation/expiry with complete execution evidence | `cancelled`; retain all fills |
| `cancel_pending` | Definitive cancellation rejection with confirmed working status | `acknowledged` if no fills, otherwise `partially_filled`; a bare denial without working-status evidence leaves `unknown` |
| `unknown` | Partial execution received before status reconciliation completes | Stay `unknown`; account for execution and retain unresolved remainder |
| `unknown` | Complete correlated reconciliation | `acknowledged`, `partially_filled`, `filled`, `cancelled` or `rejected` as evidenced; keep `cancel_pending` if cancellation remains active; otherwise remain `unknown` |

No `unknown -> reserved/submitting` transition exists. A query returning no order,
an empty open-orders list or an elapsed timeout never proves non-acceptance.
Resolving an unknown as `rejected` requires affirmative definitive rejection
evidence and zero executions. If the adapter cannot establish the outcome, remain
blocked for explicit reconciliation; do not allocate a fresh ID to retry it.

A partial execution alone may not prove a working remainder: if accompanying
status is absent/ambiguous, persist the fill and use `unknown` instead of
`partially_filled`. A status claiming cumulative fills without individual executions
is evidence of missing accounting, not permission to invent execution prices/fees.
Block entries and reconcile the execution detail before releasing resources.
Consistent corroborating status evidence may append an audited self-transition
without changing quantities, resources or permission to dispatch. It cannot clear
an unresolved reason merely by repeating an earlier status.

## Late evidence and contradictions

An acknowledgement arriving after a partial/full fill does not regress the state.
A cancel acknowledgement after `filled` is retained but cannot undo executions.
Local receipt order is not economic event order. Only evidence with adapter-defined
ordering/completeness can be classified as stale; otherwise reconcile it.

Valid late executions must be recorded even for a terminal order. For a cancelled
order they increase known executions while retaining `cancelled` for a partial
total, or change it to `filled` when total equals ordered quantity. Mark the account
unreconciled and revise the projection with an explicit reconciliation event;
this is not an ordinary reopening or a new submission. An execution contradicting
`rejected`, an overfill, a changed broker identity or a trade bust/correction is
retained as unresolved evidence and blocks entries. V1 does not silently reduce
executed quantity, rewrite history, clamp an overfill or ignore economic exposure.
Accounting that cannot yet represent the evidence remains unresolved until a
reviewed reconciliation can apply it. No subsequent admission uses that account.

Terminal status alone cannot release reservations. Missing execution detail or
fees, incomplete cash/position reconciliation and cancellation uncertainty retain
the required resources and entry block. Provisional fee bounds stay reserved;
unexpected costs update actual accounting and risk even if they exceed a planned
budget. A late fee never renews a loss allowance or clears a halt.

## Transaction and recovery boundaries for implementation

P4.2 must use one authoritative local transactional account store for the intent,
entry attempt, reservation, account/risk versions and audit. Atomic admission uses
a write transaction and expected-version checks; competing candidates cannot both
reserve the same flat-account entry slot or settled cash. Existing risk-store
migration needs its own reviewed design: no destructive conversion or reset.

A valid new entry submitted for admission consumes one of at most three session
attempt slots, including an evaluated rejection. Once all three are consumed,
further candidates are logged as limit rejections without incrementing past three.
Malformed inputs do not consume slots. Exact duplicate intent/candidate IDs do not
consume again. Cancellation, timeout, restart and broker rejection never refund
a slot. Exit attempts do not consume entry slots, but must reserve sell quantity
so simultaneous exits cannot sell more than the verified held position. Without
verified quantity, record an exposure incident rather than guessing a sell size.

Reservations subtract from available settled cash and uncommitted risk/exposure
headroom; unsettled proceeds never fund entries. On a partial fill, atomically
transfer consumed cash/reserved exposure into actual accounting and retain the
remaining order resources, exit-cost allowance and position risk. Do not count
the same allocation twice or release it merely because it changed form. P4.2 must
specify and test the numeric allocation formula against the existing diagnostic;
this state contract supplies no new loss-budget or fill-price allowance.

P4.3 serialises submission through one fenced owner. The durable dispatch marker
and command identity commit before calling the adapter. No database transaction
can make the network call atomic. Crash before/after send or lost acknowledgement
therefore yields reconciliation, never a blind replay of a submit command. A
restored database cannot prove what was sent after its backup; startup is disarmed
until external order, execution, position, cash, fee and settlement evidence agrees.
Disarmed startup prevents new order dispatch; read-only reconciliation continues.
Any exposure-management dispatch during an incident needs a separately verified
P4.5 path, not a bypass of these identity/quantity controls.

Reserved-but-unsent work survives restart but is not automatically dispatched.
Revalidate expiry, all bound versions, current quotes/FX, account reconciliation,
ownership and all halts. Changed evidence requires a new recorded authorisation
for the same never-dispatched intent, with no extra attempt slot; an expired
authorisation instead causes local cancellation and cannot be extended or renewed.
Reauthorisation before expiry must not extend the original expiry. No new authority
attaches to an already dispatch-marked intent. Persist every change with
expected-version protection.

P4.4 commits accepted execution/fee deduplication, accounting effects, reservation
adjustment, order projection, risk consequences and audit together. Durable inbox
evidence may precede that transaction; unprocessed or conflicting evidence must
block admission until applied/reconciled. Failure to persist evidence/state stops
dispatch and leaves the service disarmed; it must not report a successful cancel
or release. A missing/corrupt/unknown-version store is an error, not a new account.
Recovery replays ordered committed events and verifies projections and invariants.
No repair, halt clearance or period renewal occurs as a read side effect.

## Synthetic acceptance cases

These are required test vectors for the named implementation PRs. P4.2–P4.4 now
cover their applicable admission, writer and reconciliation portions; P4.5 cases
remain specifications. Use invented prices/IDs and a controllable clock/adapter; every
case checks persisted events, quantities, resources, attempts and dispatch counts
after reopening the store. No credentials, network or licensed bars are needed.

| ID | Scenario | Required result / implementation owner |
| --- | --- | --- |
| O01 | Approved entry, acknowledgement, two partial executions to total | States follow the table; each fill applied once; one submission; actual exposure survives `filled`. P4.2–4.4 |
| O02 | Identical proposal/event redelivered, then same key with changed quantity | Exact duplicate has no extra effect; conflicting reuse blocks entries and never dispatches. P4.2/4.4 |
| O03 | Two concurrent proposals against one flat-account entry slot/cash pool | At most one reservation; attempts/rejections and audit are atomic; no overspend or headroom over-allocation. P4.2 |
| O04 | Admission rejection, broker rejection, cancellation, restart and fourth entry | Slots are never refunded; fourth entry is blocked; daily/weekly baselines and halts unchanged. P4.2 |
| O05 | Kill before reservation commit, after reservation, before/after dispatch marker and after adapter acceptance before acknowledgement | Rollback before commit; revalidation for never-dispatched work; all possibly sent cases reconcile without a second submit. P4.2–4.4 |
| O06 | Timeout followed by empty open-order query, then a late execution | Remain unknown after empty query; preserve resources; apply late execution once; no retry. P4.3/4.4 |
| O07 | Partial fill, cancel request, more fills, cancel acknowledgement | Cancel pending survives partials; confirmed working remainder becomes zero; filled portion remains accounted/protected. P4.4/4.5 |
| O08 | Fill completes before cancel acknowledgement; rejected cancel; late acknowledgement | Filled order never regresses; cancel rejection does not reject the order; contradictory evidence blocks entries. P4.4/P4.5 |
| O09 | Cancelled order receives delayed partial/full execution or terminal rejection is contradicted | Use explicit reconciliation rules; no discarded fill, automatic resubmit or false flat claim. P4.4 |
| O10 | Duplicate execution under a new event ID, late fee, overfill, bust, missing execution detail | Deduplicate by execution identity; fees apply once; unsupported/conflicting facts remain unresolved and block entry/resource release. P4.4 |
| O11 | Missing/corrupt store, failed commit, stale version, expired authority or restored pre-submit backup | No reset/new account, dispatch or stale approval; preserve resource/attempt history and require reconciliation. P4.2–4.4 |
| O12 | Two simultaneous exits, stop rejection or lost protective-order acknowledgement | Never oversell/assume protection; persist incident; block entries while preserving verified exposure-management path. P4.5 |
| O13 | Cross account/environment ID collision, changed broker mapping, unidentified execution | No cross-account matching; retain evidence and block affected account entries. P4.3/4.4 |
| O14 | Every unlisted state/command edge, including unknown submit retry and terminal resubmit | Reject without side effects; external economic evidence uses reconciliation, not command rejection/discard. P4.2–4.4 |

## Handoff

P4.1 is complete. P4.2 implements the reviewed single-store admission/allocation
design and its portions of O02–O05, O11 and O14. P4.3 implements the single writer,
marker-before-call boundary, fenced ownership, explicit recovery and its portions
of O02, O05, O06, O11, O13 and O14. P4.4 adds external reconciliation evidence;
P4.3 does not claim its execution/accounting cases. Return to Astra for changes to these states, identity
semantics, financial invariants or uncertain-outcome rules. Connected paper and
live gates stay closed.

The [P4.5 handoff](order-protection.md#ordered-implementation-handoff) now defines
the shared sell-quantity bound, separate management permissions, cancellation
protocol, fee allocation, pending-sale accounting and incident recovery. Its
X01–X24 scenarios refine the protection and cancellation cases above. Packages A
and B implement the pure permission and durable allocation portions. Package C
implements reviewed cumulative sell accounting and pending lots in [PR #38](https://github.com/derekrivers/trad3r/pull/38);
packages D–G remain.
