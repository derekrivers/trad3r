# Protection and exposure control contract

Contract `order-protection-v1` defines the P4.5 extension to the
[order lifecycle](order-lifecycle.md). It fixes the implementation rules and
acceptance scenarios for cancellation, reducing exits, protective stops and
exposure incidents. Packages A and B implement the evaluator and capacity journal;
package C's accounting journal is delivered in [PR #38](https://github.com/derekrivers/trad3r/pull/38).
Package D's fenced synthetic cancellation is delivered in
[PR #39](https://github.com/derekrivers/trad3r/pull/39), package E dispatch in
[PR #40](https://github.com/derekrivers/trad3r/pull/40), and
[package F controls and recovery](order-controls.md) are implemented. Package G
remains an integrated acceptance specification.
P4.5 completes only when all packages pass their executable tests
and integrated fault cases.

The scope remains one synthetic account and one qualified USD equity position,
positive whole shares, and the existing risk limits. No broker, shorting,
replacement orders, native brackets, automatic incident clearance or halt reset
is introduced. All reports retain `live_trading_enabled: false`.

## Independent control facts

Do not put pause, halt, protection and flatness into one mutually exclusive enum.
A flat account can still be halted and have unsettled sale proceeds.

| Fact | Values and evidence |
| --- | --- |
| Entry control | `operator_paused` plus existing latched `halt_reasons` and open incident IDs. Each independently blocks new entries. |
| Quantity proof | `verified` or `unresolved`; account/instrument, execution watermark, snapshot ID, observed time, verified whole-share quantity and account version. No quantity proof can come from an order acknowledgement alone. |
| Exposure | `verified_flat`, `verified_long` or `unresolved`. Flat requires zero verified holdings and no reserved or possibly live entry, sell, or unresolved dispatch that could alter them. |
| Protection | `not_required`, `missing`, `pending`, `active`, `partial`, `unknown` or `rejected`, with supporting order IDs and covered quantity. A planned stop price is not active protection. |
| Desired action | `hold`, `cancel_entry_remainder` or `flatten`; a persisted objective, never dispatch authority. Flatten first prevents further entry dispatch and requests cancellation of any possibly working entry remainder. |
| Writer permission | Entry and management permissions are derived separately under the same owner and fencing epoch. Neither permits dispatch without its own current evidence and reservation. |

`verified_flat` implies protection is `not_required`. A held position is fully
protected only when correlated, current evidence proves working stop orders cover
the entire verified holding at the admitted stop price or tighter. A pending,
unknown, cancel-pending, rejected or filled stop contributes zero active coverage.
A stop limits intended behavior; it never guarantees the execution price or caps
actual loss. Gap executions must be accounted at their observed prices.

When protection is missing, uncertain or rejected, persist an incident and block
entries. A definitive rejection requests flattening; an uncertain submission
first requires reconciliation of its possible sell commitment. Do not submit a
second stop or emergency sell simply because the first acknowledgement was lost.

For package A, use a pure evaluator over a validated internal snapshot, with an
explicit UTC evaluation time. Its minimum inputs are account/environment and
instrument identity, applied account/evidence versions, snapshot time and
completeness, quantity, all known entry/sell projections and committed remainders,
confirmed stop prices, quote/FX times, fee allocations, pause/halts and open
incidents. The result includes exposure/protection states, verified and covered
quantities, committed and available sell quantities, and separate reason lists
for blocked entries, cancellations and reductions. It is diagnostic output,
not a reusable authorization token. Persisted command authorization arrives later.

Derive states deterministically. Invalid quantity/identity/completeness or a
negative capacity or a stale/future snapshot makes exposure unresolved and
available quantity unknown, not zero. Otherwise positive holdings are verified long; zero holdings are verified
flat only with no remaining reserved/possible order, and unresolved otherwise.
For protection, verified flat takes `not_required`; unresolved exposure takes
`unknown`. With verified long exposure, uncertain or cancel-pending stop remainders
take `unknown`, then full confirmed coverage takes `active`, positive incomplete
coverage takes `partial`, and queued/submitting stop remainders take `pending`.
With no coverage or pending stop, use `rejected` if the latest protection attempt
for this entry episode was definitively rejected; otherwise use `missing`. A
successful later stop can restore coverage while the earlier incident continues
to block entries until resolution.
Reject a purported coverage quantity greater than holdings as conflicting evidence.

### Package A implementation

`trad3r.order_protection` implements the pure evaluator in
[PR #36](https://github.com/derekrivers/trad3r/pull/36). Immutable typed inputs bind
the account and instrument, account/evidence versions, snapshot ID and time,
execution watermark, verified quantity, every known order remainder, stop evidence,
fee allocations, controls and incidents. `EvaluationRequest` supplies an explicit
UTC evaluation time, expected versions and optional cancel/reduction request.

The result reports those evidence bindings with exposure and protection states,
verified/covered/committed/available quantities, remaining fee allowance and
separate sorted reason lists. `entry_allowed`, `cancellation_allowed` and
`reduction_allowed` describe only that evaluation. The result is not durable and
cannot be replayed as authorization. No input parser, CLI, database, adapter or
dispatch method exists. Production callers cannot treat the input booleans as
user assertions: packages B and C must derive them from audited storage and
cumulative reconciliation.

Proof and fencing booleans default to false. A complete snapshot certifies current
position/execution evidence and an exhaustive inventory for this account's current
entry episode, including terminal orders with outstanding fees; fully resolved
prior episodes are not protection attempts for this episode. Order evidence
completeness includes current correlated working evidence where coverage is
claimed. Incomplete or uncorrelated order evidence withholds quantity proof and
retains the original quantity as a conservative commitment bound. Unresolved
exposure reports no verified quantity and zero confirmed coverage.

Entry eligibility is only this protection gate, not full entry admission: the
existing entry window, attempt, cash, policy and risk checks still apply. Both
entry and reduction gates check expected versions, fencing, fresh quote/FX and
bounded fees. Regular-session bounds come from the existing reviewed calendar;
holidays, early closes and unsupported years fail closed. The internal
`session_supported` proof must also establish that the durable account remains
in its admitted day/week; this evaluator cannot advance an account period.

Sell orders in a possibly live or incompletely terminal state retain their full
unexecuted remainder. `fee_allocation_usd` is the still-outstanding allocation for
that order, after any incurred fee has moved into the snapshot's cumulative fee
field. It remains reserved even when that order has no quantity remainder or the
account is verified flat. `other_cash_allocations_usd` includes all other current
settled-cash reservations (including entry costs), excluding the per-order exit
fees already counted. Both pools reduce the cash available for a new exit fee;
any residual allocation blocks a new entry. A fully reconciled partial entry can
be protected/reduced up to the verified holding while its bounded buy remainder
remains possible; the remainder contributes no sellable shares.
The evaluator refuses negative quantity capacity, reused fee allowance,
future/stale reduction evidence, changed versions and management-blocking incidents.
An exact mapped cancellation ignores quote/FX age and free quantity, but still
requires a valid store, current versions, a fenced writer and an evaluation time
no earlier than its snapshot.

Twenty deterministic tests implement package A's X01–X05 and X16 portions,
including pause/halt separation, flatness with possible entry work, protection
state precedence, shared stop/exit capacity, fee partitioning, partial/cancelled
remainders, terminal fee-only reservations, other cash commitments, incomplete
order proofs, session bounds, stale/future evidence and target-specific
cancellation. These tests do not claim transactional concurrency, persistence or
adapter-call coverage.

### Package B implementation

Package B in [PR #37](https://github.com/derekrivers/trad3r/pull/37) adds
`trad3r.order_allocations`, explicit fresh version-4 initialization and an
atomic reducing-allocation journal in the same SQLite order store. Version-3
initialization and reads remain unchanged; allocation commands reject v1–v3 stores
and there is no migration or downgrade command. The CLI exposes `order-v4-init`,
`order-reducing-admit`, `order-reducing-status` and `order-reducing-history`.

Each request binds its immutable allocation and client-order identities, current
account/reconciliation/writer/allocation versions, risk-policy digest, entry
episode and instrument, fenced writer owner/epoch, positive whole-share quantity,
fee bound, purpose, quote/FX times and a maximum 60-second decision lifetime. Exact duplicates
return their original record before stale-version checks. Changed identity reuse
records a blocking incident, retaining the complete conflicting request even when
its source time is stale. Duplicate incidents also precede time/version checks.
Entry and reducing identity namespaces cannot overlap; invalid cross-namespace
requests fail without a write. Stale versions or fencing also fail without a write.

New allocations require snapshot, quote and FX observations no more than 60
seconds old and not future dated, a writer event no later than the decision, and
the account's original day/week within the supported regular session. The entry
window does not restrict management. No period baseline is renewed. A current
account version must refer to a reconciled adjustment; an intervening entry
admission requires fresh reconciliation before another allocation. Package B
conservatively requires a reported commission (including explicit zero) for every
entry execution; package C extends that contract with explicit finality and
monotonic fee revisions.

The allocator derives held quantity and the original exit-fee allowance from the
complete reconciled entry evidence. Protective stops and ordinary reducing exits
consume the same pools. One `BEGIN IMMEDIATE` transaction validates replay,
reserves quantity and fees, records accepted or capacity-rejected requests, and
updates the projection. Independent concurrent requests cannot both consume the
same capacity. Allocation reads replay every digest, contiguous sequence, event
time and evidence-version ordering. Each record binds the retained snapshot,
reconciliation event, account adjustment, writer event and entry intent by digest.
Replay derives holdings, original fee allowance and cash backing from these inputs
and compares every capacity decision and aggregate with the stored projection.
Missing inputs and coherently rehashed capacity projections fail closed across
account, writer, reconciliation and allocation reads. This is single-buy capacity
replay; independent replay of all multi-order accounting effects belongs to C.

Identity incidents block new entry admission, writer claims and submission
markers while preserving exact retries. Allocation status explicitly reports
`capacity_scope: at_last_allocation_decision` and `dispatch_authorized: false`:
its historical capacity is not a current permission or exposure evaluation.

Allocations do not consume entry attempts or clear halts, entry exposure/loss
reservations, incidents or writer controls. They never expire or release capacity
implicitly; later packages must prove executions, cancellation and terminal fee
evidence before changing these commitments. This package has no reducing adapter,
submission marker, cancellation, sell reconciliation, pending proceeds or live
path. Nineteen deterministic tests cover the package-B portions of X04, X15 and X23,
including exact fee partitioning, concurrent full-quantity requests, fencing,
rollback, restart/replay corruption, stale/future/session bounds, retained source
evidence, cross-namespace identities, account-wide blocking and version-3 compatibility.

### Package C implementation

Package C adds `trad3r.order_sell_reconciliation` to freshly initialized v4
stores. `order-reducing-reconcile` accepts a complete cumulative synthetic
snapshot containing the retained entry order and every observed allocated sell;
the status and history commands are read-only. This is an evidence/accounting
boundary with no adapter or dispatch method.

Every applied snapshot binds the exact writer event, allocation event, prior
account version and retained P4.4 entry evidence. Replay independently derives
buy cost, settled cash, holdings, possible sell remainders, fees, pending lots,
reservations, risk latches and the account adjustment. Rehashed entry prices,
account projections, event identities or authority evidence fail closed.

Sell executions reduce both verified holdings and their allocation's possible
remainder. An absent, working or unknown allocated sell retains its full possible
remainder. Unknown orders, changed executions, overfills, source-time conflicts,
negative capacity and manual activity retain the full incoming snapshot and latch
an incident without replacing the last verified account facts. Ordinary snapshots
cannot clear those incidents; recovery belongs to package F.

Every execution requires an explicit fee record with a `final` flag. Missing fees
use the allocation's conservative bound for the pending-lot projection; provisional
and missing fees update verified quantity but retain the original exit allowance,
entry exposure/loss reservations and an entry block. A monotonic final revision
updates the same execution lot once. Actual final fees may exceed the plan and
reduce pending proceeds; they never enlarge the allowance.

Each sell execution produces one execution-keyed pending lot with gross, applied
fee, net amount, scheduled settlement date, conservative availability cutoff and
the existing policy identifiers. Settled cash excludes every lot. No clock,
restart or snapshot releases it, and package C provides no release command.

Version 4 currently supports one protected entry episode. After that episode is
fully sold, `reducing_episode_transition_required` blocks another entry because
package C cannot bind it to a fresh allocation history. The pending lot is not
the cause of that block. A reviewed episode transition remains later scope.

Nineteen deterministic package-C tests cover partial/full and multi-order remainders, duplicate
envelopes, fee finality/revision, pending cash, working/unknown orders, identity
and manual-activity incidents, non-recovery, rollback, replay corruption, restart
and v3 isolation.

Critical review added ordered incident replay, retained-input hash and SQL identity
checks, required writer-disarm linkage, event-time checks and rejection of unaudited
inbox rows. Later evidence cannot rewrite an earlier incident's classification.
Entry-fee revisions debit settled cash; provisional entry fees retain any unused
entry allowance even after the last share sells. Entry and reducing reconciliation
IDs share a collision boundary. These corrections are included in PR #38.

The current allocator still requires P4.4 entry evidence. Allocating or releasing
new reducing capacity after cumulative sell accounting needs the later cancellation
and dispatch packages to bind the current cumulative proof. Existing allocations
remain historical reservations; status is not new management authority.

### Package D implementation

Package D adds `trad3r.order_cancellation` and the
[fenced cancellation contract](order-cancellation.md) to fresh v4 stores. A request
binds the exact known order, owner/epoch, decision/expiry and all current account,
writer, allocation and reconciliation versions. It needs no quote, FX or free
quantity. The committed marker disarms the shared writer before the synthetic
adapter is called, and exact duplicates never call it again.

Accepted responses remain unresolved until cumulative entry or reducing evidence
proves `cancelled` or `filled`. Bare denials and lost responses remain unknown;
confirmed rejection with working status restores the evidenced working outcome.
Partial fills retain the full residual commitment. No response directly changes
cash, quantity, risk, fees or settlement, and late responses cannot regress a
filled order.

The separate journal replays retained inputs, SQL identities, writer fencing and
the exact reconciliation snapshot behind each evidence transition. Identity
conflicts latch, marker/result writes are atomic, and a failed result commit leaves
the marker in place so restart cannot cause a blind retry. Twelve deterministic
tests cover the package-D portions of X07–X10, X15–X16 and X23. X13's complete
stop-to-exit flow remains with reducing dispatch and integrated packages E–G.

## Verified management authority

Management permissions may survive an entry pause, a loss halt, or a protection
incident. They do not bypass corrupted storage, contradictory identities,
unverified holdings, ambiguous external orders or stale evidence.

Every new reducing-order authorization binds the immutable intent and command,
account/instrument, policy digest, account/reconciliation/control versions,
quantity proof and evidence digest, current writer scope, explicit fee bound,
decision time and expiry. Use the existing maximum 60-second authority lifetime
and evidence age. Quantity evidence, quote and FX observations cannot be future
dated. Dispatch revalidates all bindings under the writer lock. Reductions are
allowed outside the entry window, within the supported regular exchange session;
they do not renew a session or week. Unsupported sessions remain blocked.

A known order with unknown acceptance or cancel outcome can coexist with a
verified quantity proof only if complete execution/position evidence and an
exhaustive known-order inventory establish its maximum possible sell remainder.
That entire remainder stays committed. Unknown external activity or missing
execution detail invalidates the proof. Unbounded or contradictory cash/fee
exposure also blocks a new sell authorization; it need not prevent cancelling a
uniquely identified order. A pending final fee report can use its already persisted
conservative allowance for management only when confirmed settled cash covers
every outstanding allocation. Final fee completeness still gates new entries.

A cancel authorization binds the exact known order, immutable cancellation
operation ID, current versions, owner/epoch and its own decision/expiry. Cancelling
a uniquely identified possible order needs no quote or free sell quantity. It
never inherits an expired entry authorization. A safe cancellation can therefore
be permitted while new submissions remain disarmed. An unknown mapping permits
read-only reconciliation and incident reporting only.

These are explicit permission checks, not a caller-controlled `force` or
`ignore_halts` flag. On startup no permission exists until evidence has been
validated and a fenced management or ordinary writer claim has committed.

## Sell quantity and cost reservation

Let `Q` be the verified held quantity at the applied execution watermark. For each
sell intent `i`, let `q_i` be its immutable original quantity and `f_i` its unique,
already-accounted executed quantity. Its committed remainder is:

- `q_i - f_i` while reserved, submitting, working, partially filled, unknown or
  cancel pending;
- zero only after a proved pre-dispatch withdrawal or complete authoritative
  evidence that no unexecuted remainder can fill.

Available quantity is `Q - sum(committed remainders)`. Admission must reserve a
positive integer no larger than that availability in the same account transaction.
A negative result is an incident, never clamped to zero. Count protective stops
and ordinary reducing sells together. Different client IDs and operation IDs do
not create extra capacity. Exit admissions consume no entry attempts.

When a sell execution of `k` shares commits, both `Q` and that order's remainder
decrease by `k` atomically. Unknown unreported fills remain covered by the full
possible remainder; no acknowledgement, timeout or cancellation request releases
that bound. An execution beyond the bound is retained as conflicting evidence and
blocks new dispatch; do not silently invent a short position or discard the fill.

Bind a settled-cash fee allowance to each reserved exit. Partition the entry's
original exit-fee allowance between incurred exit fees and outstanding allocations;
never count the same allowance twice. A new authorization cannot make their sum
exceed that original bound. A partial fill, cancellation or new exit ID cannot
replenish it. If proposed
fragmented exits need more fees than the original plan permits, record an incident
and withhold those submissions; this contract grants no larger planned-risk budget.
Actual unexpected charges may exceed that bound and must still enter accounting
and risk assessment; they do not authorize another allocation. Keep the
entry's original exposure/loss allocations conservatively until the position and
entry remainder are gone and fees are accounted; do not prorate them merely
because a stop exists. A fee-only residual can remain after verified flatness.
No exit creates fresh loss headroom or refunds an entry attempt.

## Cancellation and exit races

Cancellation is an operation on an existing order, not a new order. Persist its
payload/digest, target, owner/epoch, marker, outcome and receipt evidence separately
from submission. The original order retains its cumulative executions and last
confirmed state. Only one unresolved cancellation operation may exist per target;
duplicate requests return its current status without another adapter call.

| Observation | Required effect |
| --- | --- |
| Cancel marker commits | Set `cancel_pending`; preserve all possible remainder and costs. Only then call the synthetic adapter. |
| Partial execution during cancel | Apply it once; keep cancel pending and the residual commitment. |
| Executions reach original quantity | Mark filled; pending cancellation becomes moot. Its later response remains audited. |
| Adapter says cancel accepted | Record response; release nothing until cumulative order, execution and position evidence proves the terminal remainder. |
| Definitive cancel rejection with working evidence | Restore acknowledged/partially filled order state, retaining its remainder. The order itself is not rejected. |
| Bare denial, timeout or failed result commit | Preserve uncertainty and resources; reconciliation required. No blind cancel retry after a dispatch marker. |
| Cancelled order receives valid late fills | Reconcile them once. If they conflict with capacity assigned to another exit, retain a durable incident and disarm; ordinary snapshots cannot clear it. |

To replace a protective stop with an ordinary exit, first persist the flatten
objective, cancel the stop, reconcile its executions and terminal remainder, then
reserve a newly calculated exit quantity. Both commands cannot claim the same
shares. The interval with no confirmed protection is an explicit incident, not
an assertion that the account remains protected. If the stop fills during cancel,
reduce or omit the later exit according to the freshly verified position.

The synthetic protective command is a whole-share day sell stop at the bound
stop price; the ordinary reducing command is a whole-share day sell limit with an
explicit price bound. Their adapters consume supplied outcomes and executions;
they do not infer market fills. A triggered unfilled stop, day expiry, or unfilled
limit remains an exposure obligation. No market-order fallback, widened stop or
automatic price replacement is approved by this contract.

## Accounting and settlement

Extend cumulative evidence to multiple related entry/exit orders while preserving
one position. Account quantity is cumulative accepted buys minus accepted sells.
All executions and fee revisions retain stable identities across snapshots;
one order's reconciliation cannot overwrite another's reservation. Retain full
conflicting inputs as well as their digests. Source times must be compatible with
the synthetic dispatch and snapshot times; receipt/commit order is separately
recorded so valid late evidence does not have to arrive in source-time order.

Fee completeness must be explicit for each execution, including an explicit zero
charge when applicable. Absence of a fee record is not zero. Retain provisional
allowances and block new entries until fees reconcile; a higher valid revision
still applies once after a prior completeness assertion. Actual fees and fresh
marks can add halts even when costs exceed the planned budget.

Each sell execution creates a pending USD lot keyed by execution ID, with gross
proceeds, applied fee revisions, net proceeds, scheduled date and availability
cutoff. Follow the existing [settlement contract](settlement.md): fees reduce the
pending proceeds; they do not also debit settled cash. A later fee revision changes
the same pending lot, or debits settled cash if a separately authorized settlement
release has already occurred. Unsupported negative net proceeds remain a retained
incident requiring reviewed accounting, not a dropped execution.

Use `settlement_date` and `cash_available_at` with their existing policy IDs.
Settled cash never includes pending lots. Flatness does not imply settlement,
entry eligibility or release of a halt. A matched pending lot alone need not
block an entry funded wholly by other available settled cash.

P4.5 persists and reconciles pending obligations but does not implement a durable
cross-period cash release. The current durable store refuses day/week transitions;
P4.6 must settle that policy before release can be enabled. Crossing midnight,
restarting or reaching the calendar cutoff is never an implicit settlement or
baseline reset. Pure calendar tests can verify future due dates without advancing
a durable account.

## Incidents and manual intervention

An incident records a stable ID, kind, full evidence references, observed and
committed times, affected order/intent IDs, last verified quantity, possible sell
commitments, reason for withholding permission and desired action. Report verified
facts separately from conflicting reported exposure. No alert or notification
delivery is implied by persistence.

Protection failure and requested pause can coexist with an otherwise verified
management path. Unknown external activity, unsupported corrections, overfills,
conflicting reservations or broken audit state withhold quantity authority until
explicit recovery establishes consistent evidence. Uncorrelated manual trades
follow the same rule; do not silently adopt them as ordinary fills.

Manual recovery is an append-only resolution referencing the incident, a complete
new reconciliation and expected versions. It requires a separately authorized
owner control event; an AI cannot approve itself by putting `actor: owner` in a
payload. Synthetic tests can inject that trusted control through a test-only
boundary. Recovery may acknowledge a resolved incident or resume an operator
pause; it cannot erase evidence, alter policy, clear a loss halt, renew budgets,
refund attempts, or claim flatness without the required quantity/order proof.
Recovery does not itself dispatch. Unsupported accounting repair stays blocked.

### Package F implementation

[Durable controls](order-controls.md) add a replayed v4 journal for operator pause,
desired action and protection incidents. Evidence mutations and protection
observations commit atomically. Entry gates honor controls independently of the
fenced management path. Recovery requires fresh complete evidence newer than the
affected incident/pause and a separately injected synthetic owner event. There is
no production owner authenticator or recovery CLI; no halt, budget, attempt,
objective, cash or writer authority is reset. Durable accounting repair stays
blocked. Package G remains the integrated acceptance gate.

## Storage and replay boundary

Implement this extension as a new explicitly selected version-4 synthetic order
database in the existing authoritative store architecture, not a second database
beside it. Keep version-3 behavior readable and unchanged. New initialization must
use a fresh path; never recreate an existing account to clear its history. There
is no automatic v3 migration or downgrade. A history-preserving migration is a
separate reviewed task before existing v3 accounts can use P4.5.

Use one write transaction for each admission or evidence application: immutable
inputs, deduplication, per-intent allocations, executions/fees, account quantity,
cash/pending lots, risk consequences, incident/control state, writer projection
and audit must agree. Marker-before-call remains a separate transaction from the
adapter result. All callers validate digests, sequence and reconstructed state
before deriving permissions. Replay must link retained input evidence to derived
effects, extending the present v3 checks rather than claiming they already do so.

Exact durable duplicates precede freshness/version checks and never grant another
adapter call. Failed persistence, unsupported database versions and missing or
contradictory evidence fail closed. Reads cannot repair, dispatch or clear controls.

## Numeric acceptance fixture

Use invented values from `tests/test_order_reconciliation.py`: $500 settled cash,
£1,000 equity/session/week baselines, GBP per USD `0.8`, a two-share entry at limit
`100`, stop `99.5`, slippage `0.05`, entry fee `0.35` and exit fee `0.35`.
Initial allocations are $200.80 cash, £160.08 exposure and £1.52 planned loss.

One buy at $100 with a final $0.35 entry fee leaves $399.65 settled cash and one
share. While its other share can still fill, cash reserve is $100.40. Confirming
cancellation of that entry remainder reduces the reserve to $0.35; the held share
and conservative original risk allocations remain. A stop for one share commits
that share, so a concurrent one-share ordinary exit has zero available quantity.

If the stop is confirmed cancelled without executions, a new one-share exit may
reserve it. Selling at $99.50 with a final $0.35 fee leaves zero holdings,
$399.65 settled cash and a $99.15 pending lot. Total USD cash plus receivables is
$498.80. With complete terminal/fee evidence all three
entry allocations can release. Entry attempts and all loss latches stay unchanged.
For a 4 September 2026 sale, the existing calendar yields 8 September settlement
and a 9 September 04:00 UTC research cutoff; P4.5 does not execute that release.

## Required acceptance scenarios

These are test specifications, not currently passing runtime tests. Each applicable
case must assert persisted history, quantities, allocations, cash/pending lots,
attempts, halts, returned permissions and synthetic adapter call counts after
reopening. Use deterministic virtual times, invented identities and injected faults.
Run concurrency cases with independent connections; do not mock away transactions.

| ID | Scenario and required result | Package |
| --- | --- | --- |
| X01 | Paused and daily-halted account with verified holdings: block entry; permit a fully evidenced reduction with free capacity; preserve every halt and attempt. | A, E, F |
| X02 | Flat, halted account with pending sale cash: flat/not-required protection, halt remains, pending cash unspendable. A paused flat account is still paused. Zero holdings with a reserved or possibly live entry is unresolved exposure/unknown protection, never verified flat or active protection. | A, C, F |
| X03 | A stop price in an entry proposal, then a queued/acknowledged stop: coverage remains zero until complete correlated working evidence; assert pending then active. | A, E |
| X04 | Two distinct concurrent exits each seek all two held shares: exactly one reserves two, the other cannot dispatch; entry attempts unchanged. Two one-share requests may reserve one each with fee bounds $0.15 and $0.20; two $0.35 fee bounds cannot reuse the original $0.35 allowance. | B, E |
| X05 | Stop already commits all shares: another exit cannot reserve them, including while the stop is submitting, unknown or cancel pending. | A, B, E |
| X06 | Two-share sell with one accounted fill: holdings and committed remainder both move 2 to 1, free capacity remains zero; duplicate fill under another envelope changes nothing. | C |
| X07 | Numeric fixture partial entry, cancel request, one more entry fill, then cancel response: original two-share holding survives, cancellation releases no executed exposure. | C, D |
| X08 | Fill completes before cancel response: order stays filled; later acknowledgement cannot restore quantity or authorize another exit. | C, D |
| X09 | Cancel rejected with working evidence versus bare denial: restore working state only in the first case; retain the full possible remainder in both. | D |
| X10 | Crash before cancel marker, after marker, after adapter acceptance and during result commit: at most one call; possibly sent cases require reconciliation; injected failure rolls back all local effects. | D, G |
| X11 | Stop definitively rejected: incident, zero active coverage, entries blocked; after complete rejection/fee evidence a newly verified reducing exit can reserve the shares. | E, F |
| X12 | Stop accepted but acknowledgement lost: unknown coverage with full sell commitment; empty open-orders query cannot free shares or authorize a replacement. | C, E |
| X13 | Stop-to-exit sequence, with stop filling during cancellation: new exit uses only freshly verified residual shares, or is omitted at zero; no overlap. | D, E, G |
| X14 | Cancelled stop reports a late fill after another exit reserved capacity: retain both identities and full incoming evidence, open a durable capacity incident, disarm; do not clamp or clear on ordinary retry. | C, F |
| X15 | Exact duplicate exit/cancel/resolution with stale expected versions: return current state, no extra call/attempt/allocation; changed reuse records a blocking conflict. | B, D, F |
| X16 | Stale quantity proof/quote/FX, future-dated evidence, wrong instrument or external unknown order: no reducing dispatch. A uniquely identified cancellation can still proceed without a quote or free shares. | A, D, E |
| X17 | Sell in numeric fixture: settled $399.65, pending $99.15, zero holdings; duplicate execution or snapshot does not credit again. A provisional/missing fee retains allowance and blocks entries until explicit completion. | C |
| X18 | Final sell fee revised $0.35 to $0.45: pending lot becomes $99.05 once; settled cash remains $399.65. Fresh £989 mark adds daily halt, and a later £1,000 mark cannot clear it. | C |
| X19 | Calendar cutoff reached or process restarted with pending proceeds: no automatic credit. Durable cross-day application stays refused until P4.6; pure calendar tests cover holidays and unsupported years. | C, G |
| X20 | Manual/unidentified sell, overfill, trade bust or quantity mismatch: retain evidence and last verified facts, withhold management quantity permission and entry permission; no guessed flatten. | C, F |
| X21 | Owner resolution without complete current evidence, AI-forged owner label, or attempted halt/budget reset: reject without clearing controls. Valid resolution remains audited and never dispatches itself. | F |
| X22 | A sell remains working without fills, stop gaps below its price, or day expiry leaves holdings: never infer success/flatness; account supplied adverse fills and keep unresolved protection visible. | C, E, F |
| X23 | Lost writer ownership, stale epoch, corrupt evidence/projection or storage failure: no adapter call under stale authority; every committed effect reconstructs after restart. | B, D, E, G |
| X24 | Full numeric cancellation-to-exit trace, including pause and a prior halt: unique dispatches, no oversell, correct pending proceeds, verified flat, no refunded attempts or cleared halt. | G |

## Ordered implementation handoff

These packages refine P4.5; they do not add or renumber master-plan tasks. Take
one focused PR at a time. Start each implementation with Sol High; return to Astra
for ambiguity or changes to financial, identity or uncertain-outcome semantics,
and for final review of those critical diffs. A model change requires the user's
model selection; neither a written model assignment nor self-review is independent
approval. Every merge still requires the repository's reviewed-head CI controls.

| Package | Bounded deliverable and dependencies | Completion boundary |
| --- | --- | --- |
| A | **Complete:** pure protection/quantity/permission evaluator and 20 deterministic tests; [PR #36](https://github.com/derekrivers/trad3r/pull/36). | X01–X05/X16 fact and permission portions; explicit reasons, no persistence or dispatch claim. |
| B | **Complete in [PR #37](https://github.com/derekrivers/trad3r/pull/37):** explicit fresh v4 initialization, authoritative quantity/fee allocations, retained-input replay and atomic reducing admission; Astra review fixes included. Depends A. | X04/X15/X23 reservation/storage portions; 19 deterministic tests, preserve v3 reads, no migration or enabled dispatch. |
| C | **Complete in [PR #38](https://github.com/derekrivers/trad3r/pull/38):** v4 cumulative multi-order buy/sell reconciliation, execution-level fee completeness, pending lots and retained contradictions, including critical review fixes. Depends B. | X02/X06/X14/X17–X20/X22 accounting portions; 19 deterministic tests, no durable period transition or cash-release command. |
| D | **Complete in [PR #39](https://github.com/derekrivers/trad3r/pull/39):** separate fenced cancellation operation and deterministic adapter outcomes, integrated with cumulative evidence. Depends C. | X07–X10/X13/X15/X16/X23 cancellation portions; no release from an acknowledgement alone. |
| E | **Complete in [PR #40](https://github.com/derekrivers/trad3r/pull/40):** fenced synthetic reducing-limit and protective-stop dispatch, durable marker-before-call, exact replay and cumulative broker correlation. Depends D. | X01/X03–X05/X11–X13/X16/X22/X23 dispatch portions; 14 deterministic tests, no network or fallback market orders. |
| F | **Complete in [PR #41](https://github.com/derekrivers/trad3r/pull/41):** [durable pause, desired action, protection incidents and evidence-bound synthetic owner recovery](order-controls.md). Depends E. | X01/X02/X11/X14/X15/X20–X22 control portions; no halt/budget reset or invented owner authentication. |
| G | Integrated restart, concurrent exits, cancel/fill faults and full lifecycle rehearsal. Depends A–F. | All X01–X24 executable with actual store/writer integration; map O07/O08/O12 and other overlapping lifecycle cases to test names. |

The pure evaluator completes A only. P4.5 remains in progress until G passes and
the documentation names the integrated evidence. Connected
paper remains P5; durable period policy remains P4.6; existing-account migration
and external incident repair require separate reviewed designs.
