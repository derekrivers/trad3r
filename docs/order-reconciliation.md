# Synthetic order reconciliation

P4.4 adds durable cumulative reconciliation to version-3 and fresh version-4
synthetic order databases. It has no network client or broker endpoint. Callers supply a complete
snapshot of orders, executions, USD cash, positions, commissions and settlement;
the store validates their agreement before it changes account or order state.

## Commands

```sh
python -m trad3r order-reconcile-invalidate runs/orders.sqlite examples/order-reconciliation-invalidation.json
python -m trad3r order-reconcile runs/orders.sqlite examples/order-reconciliation.json
python -m trad3r order-reconciliation-status runs/orders.sqlite
python -m trad3r order-reconciliation-history runs/orders.sqlite
python -m trad3r order-reducing-reconcile runs/orders.sqlite /path/to/reducing-snapshot.json
python -m trad3r order-reducing-reconciliation-status runs/orders.sqlite
python -m trad3r order-reducing-reconciliation-history runs/orders.sqlite
```

Startup recovery and explicit disconnect invalidation clear writer ownership,
disarm dispatch and add `reconciliation_required`. A later writer claim is rejected
until a complete, consistent snapshot has committed. Recovery never treats an
empty order query as proof that a possibly submitted order was rejected.

## Evidence contract

`synthetic-reconciliation-snapshot-v1` is cumulative. Each snapshot declares
completeness independently for orders, executions, positions, currency cash,
commissions and settlement. It carries stable snapshot and reconciliation IDs,
the expected reconciliation version and one account namespace. Exact redelivery
is idempotent even after versions advance. Reusing an identity with different
content records a durable incident and keeps the writer disarmed.

The P4.4 adapter boundary supports the current admission scope: one synthetic USD
long-entry order and positive whole-share buy executions. Every execution must
have a stable ID and match the client order, broker order and qualified instrument.
Every commission has its own ID, execution link and monotonic revision. Snapshots
must retain earlier executions and commissions; disappearance or changed identity
facts is an incident. A higher commission revision may replace its amount once.

A complete snapshot must satisfy all of these checks:

- individual executions sum to the order cumulative quantity and never overfill;
- `filled` accounts for the full order and `rejected` has no execution;
- position quantity and identity agree with cumulative executions;
- USD cash equals the initial cash less execution notionals and current commissions;
- the current entry-only scope has zero unsettled USD and no pending settlements;
- a terminal order does not regress, while a partially executed cancelled order
  may later become filled from valid cumulative late evidence.

Cash and settlement checks also apply when no order has been dispatched. An
`expired_authority` record proves that local authority expired before dispatch;
it stays unchanged and does not require a broker-order row. External evidence for
that never-dispatched order remains an incident.

Incomplete observations and correctable cash, position or status disagreements
remain unresolved and can be cleared by a later complete snapshot. Changed stable
identities, overfills, unknown external activity and terminal-state regressions
are durable incidents. They are never cleared by a later ordinary snapshot.

## Atomic effects and replay

For accepted evidence, one SQLite transaction commits the inbox snapshot,
execution and commission deduplication, account cash and position, remaining cash,
exposure and planned-loss reservations, risk-latch consequences, account audit,
order projection, writer disarm and reconciliation event. An injected failure at
any write rolls the whole transaction back.

Partial fills reserve the unfilled quantity at the admitted limit plus slippage,
any unused entry-fee allowance, the exit-fee allowance, and the original exposure
and planned-loss allocations. A full fill retains its exit-fee allowance and its
position risk. A confirmed rejection or unfilled cancellation releases all three
allocations. Attempts are never refunded. New marks may add daily, weekly or
overall halts; reconciliation cannot clear a latched halt.

A consistent empty-order snapshot also commits its mark, risk halts and account
version. Its account adjustment has `intent_id: null` and preserves every current
reservation. An old terminal order with no fills cannot release a newer admission's
cash, exposure or loss allocation. If late evidence instead implies exposure for
the old order, `reservation_owner_conflict` blocks reconciliation and dispatch;
the inbox retains the evidence and the account projection remains unchanged for
explicit recovery. A later ordinary snapshot cannot clear that incident.

Reads reconstruct account reservations and writer transitions from their audit
histories, validate reconciliation event digests and sequence, and compare stored
projections. Account audit replay checks that an adjustment without an intent, or
for a different intent, cannot change the current reservation. These checks are
not yet a full independent replay of every inbox snapshot into derived accounting.
Missing state, unknown database versions and detected projection mismatches fail
closed. Existing version-3 history remains readable. Fresh version-4 stores retain
this entry reconciliation while adding the P4.5 reducing-allocation journal; older
code cannot read new account-only adjustments with a null intent and must not be
used to downgrade either version.

## Scope limit

The settlement field is required and reconciled as empty for the current entry-only
writer. Position-reducing sell commands and pending proceeds are specified in the
[P4.5 protection contract](order-protection.md); durable cross-day cash release
depends on P4.6's reviewed period policy. In the current v3/v4 entry reconciliation, any
pending settlement blocks reconciliation.
Version-1 and version-2 stores stay readable by their earlier components but need
an explicit version-3 migration before reconciliation. Existing v3 accounts also
need a separate reviewed history-preserving migration before using v4 reducing
allocations. No automatic migration,
connected paper mode, cancellation dispatch, protection order or live mode exists.

## Version-4 reducing reconciliation

P4.5 package C extends a fresh v4 store with a separately replayed cumulative
buy/sell projection while retaining the P4.4 entry inbox. Once sell evidence has
begun, the entry-only apply command refuses further snapshots; subsequent evidence
must use the comprehensive reducing schema so entry reconciliation cannot overwrite
accounted sells.

The reducing snapshot lists all current-episode orders, executions, fee revisions,
position, settled USD and pending lots. Buy history must extend retained P4.4 facts
without changing them. Sell orders map to package-B allocations. Every latest fee
record states whether it is final. Missing/provisional fees use reserved bounds and
block entries while allowing known quantity to be accounted conservatively.

Accepted evidence atomically adds an account adjustment and reducing event.
Settled cash equals initial cash less cumulative buy notionals and buy fees; sale
proceeds remain in execution-keyed pending lots. The existing T+1 calendar and
conservative availability cutoff are persisted, but no release is implemented.
After a fully sold episode, a separate episode-transition block prevents another
entry until later work can bind fresh entry and allocation history; pending cash
is not treated as settled or as the transition blocker.

Changed identities, manual orders, overfills, negative capacity and altered history
are durable incidents. Incomplete snapshots do not change account facts. Exact
duplicates precede version checks. Every read replays retained input and checks
writer/allocation evidence, the prior account version, output adjustment and event
digests. V3 behavior and schema remain unchanged.
