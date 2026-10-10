# Synthetic order reconciliation

P4.4 adds durable cumulative reconciliation to the version-3 synthetic order
database. It has no network client or broker endpoint. Callers supply a complete
snapshot of orders, executions, USD cash, positions, commissions and settlement;
the store validates their agreement before it changes account or order state.

## Commands

```sh
python -m trad3r order-reconcile-invalidate runs/orders.sqlite examples/order-reconciliation-invalidation.json
python -m trad3r order-reconcile runs/orders.sqlite examples/order-reconciliation.json
python -m trad3r order-reconciliation-status runs/orders.sqlite
python -m trad3r order-reconciliation-history runs/orders.sqlite
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
closed. Existing version-3 history remains readable; older code cannot read new
account-only adjustments with a null intent and must not be used to downgrade it.

## Scope limit

The settlement field is required and reconciled as empty for the current entry-only
writer. Position-reducing sell commands and their T+1 proceeds arrive with P4.5;
until that extension is reviewed, any pending settlement blocks reconciliation.
Version-1 and version-2 stores stay readable by their earlier components but need
an explicit version-3 migration before reconciliation. No automatic migration,
connected paper mode, cancellation dispatch, protection order or live mode exists.
