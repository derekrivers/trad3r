# Atomic synthetic order admission

P4.2 implements `order-admission-v1` in a new, broker-neutral SQLite store. P4.3
now extends newly created stores with the separate [synthetic writer](order-writer.md).
Admission itself
persists a synthetic account snapshot, immutable order identities, entry attempts,
cash/risk reservations, identity incidents and an audit sequence in one local
transaction. It has no network, fill or broker reconciliation method.
Every result states `live_trading_enabled: false`.

This store is the implementation foundation for the
[durable order lifecycle](order-lifecycle.md). It does not migrate or wrap the
existing risk database and in-memory ledger: separate stores cannot honestly make
account admission atomic. A later reconciliation design must import their history
without resetting funding, loss baselines or halts.

## Synthetic walkthrough

Use a new database path. Existing paths are never replaced:

```sh
python -m trad3r order-init runs/orders.sqlite examples/order-account.json
python -m trad3r order-admit runs/orders.sqlite examples/order-entry.json
python -m trad3r order-status runs/orders.sqlite
python -m trad3r order-history runs/orders.sqlite
```

The supplied example begins with caller-asserted, invented $500 settled cash and a
£1,000 mark. Its one-share AAPL proposal reserves $100.75 settled cash, £80.04
exposure and £2.24 planned loss. These numbers are synthetic control fixtures, not market
observations, performance evidence or authority to place an order.

`order-init` accepts only an explicitly `synthetic` environment and a flat account.
The snapshot binds account, ledger, risk and evidence versions; GBP mark and
session/week baselines; all latched loss reasons; settled USD cash; and one supported
2026 session. It checks risk arithmetic and shape but cannot independently reconcile
that starting cash/mark assertion; P4.4 owns that evidence. Triggered loss reasons
must already be complete. A missing, corrupt,
wrong-version or policy/calendar-mismatched database fails rather than creating or
repairing an account.

## Admission and allocation

V1 accepts only whole-share USD long-entry day-limit proposals. Each proposal binds
one account/environment, intent, producer candidate and client-order identity;
instrument, quantity and economics; decision/expiry and quote/FX times; plus exact
account, ledger, risk and evidence versions. The expiry must be after the decision
and no more than 60 seconds later. Account, quote and FX evidence must be no later
than the decision and at most 60 seconds old. The supported entry window and
calendar remain the existing New York 10:00–11:29:59 and reviewed 2026 sessions.

For quantity `q`, limit `e`, stop `p`, per-share adverse allowance `s`, GBP per USD
`fx`, and explicit entry/exit USD fees:

- cash reservation = `q × (e + s) + entry fee + exit fee`;
- exposure reservation = `q × (e + s) × fx`;
- planned-loss reservation = `q × ((e + s) - (p - s)) × fx + both fees × fx`.

The transaction checks the existing £3 planned-loss cap, £500 exposure cap,
settled cash and remaining overall/session/week loss headroom. Reserved amounts
reduce the corresponding availability. Unsettled proceeds are not an input. V1
has one flat-account entry slot, so only one entry reservation can be open.

A valid evaluated entry consumes one of three session attempt slots whether it is
reserved or rejected. Once three are consumed, later valid proposals are recorded
as `entry_attempt_limit` rejections without increasing the count. Cancellation,
timeout, broker rejection and restart will not refund attempts when later phases
add those events. Malformed inputs, stale expected versions and changed bound
ledger/risk/evidence versions fail before evaluation and write nothing.

## Identity, retries and durability

An exact retry is checked before its now-stale expected account version and returns
the current account status with `duplicate: true`. It does not add an attempt,
reservation or audit event. Reusing an intent, candidate or client-order identity
with changed payload creates a durable `identity_conflict` incident. The incident
blocks subsequent entries and repeated delivery of the exact conflict is itself
idempotent.

SQLite `BEGIN IMMEDIATE`, expected versions, `synchronous=FULL` and a single audit
sequence serialize competing writers. Intent, attempt, all reservations, incident
and state changes commit or roll back together. Reads reconstruct attempts,
reservations, incidents and every audit digest from the durable rows. Disagreement,
sequence holes or integrity errors fail closed. This detects inconsistent data; it
does not provide cryptographic protection against a privileged actor coherently
rewriting the entire database. Use a local filesystem and protected backups.

An accepted intent stops in `reserved`. Expiry is stored and immutable. The P4.3
writer rechecks expiry, every bound version, evidence age, halts and fenced
ownership. It locally cancels and releases a never-dispatched expired reservation
without refunding its attempt, and writes an operation tombstone so it cannot be
submitted later. It cannot extend, renew or silently discard the authority.

## Verified scope and next work

Deterministic tests cover the P4.2 portions of O02–O05, O11 and O14: duplicate and
conflicting identity, concurrent admission, attempt exhaustion, restart, stale
versions/evidence, expiry binding, storage rollback, corruption and invalid input.
They also check each resource limit and latched loss rejection. Tests use only
invented inputs.

P4.3 now supplies the [single fenced writer](order-writer.md), durable dispatch
marker and synthetic adapter. It never submits automatically on restart or retries
a possibly sent command. P4.4 then applies broker events and
accounting/reconciliation atomically. P4.5 owns
position-reducing exits and protection incidents. Connected paper and live gates
remain closed.
