# Synthetic single-writer submission

P4.3 implements a fenced, durable writer on the P4.2 order database. It can call
only the in-process deterministic synthetic adapter. There is no URL, credential,
socket, broker SDK, paper endpoint or live mode. Every report retains
`live_trading_enabled: false`.

The writer proves the submission boundary where a local transaction and an
external call cannot be atomic. It commits the exact command and operation ID
before invoking the adapter. After that marker exists, the operation is never
submitted again. An acknowledgement timeout, a failed result commit or recovery
of an in-flight marker requires reconciliation under P4.4.

## Synthetic walkthrough

Create and admit a fresh example as described in
[atomic admission](order-admission.md), then claim one writer epoch and submit:

```sh
python -m trad3r order-init runs/orders.sqlite examples/order-account.json
python -m trad3r order-admit runs/orders.sqlite examples/order-entry.json
python -m trad3r order-writer-claim runs/orders.sqlite examples/order-writer-claim.json
python -m trad3r order-dispatch-synthetic runs/orders.sqlite examples/order-submission.json --outcome acknowledged
python -m trad3r order-writer-status runs/orders.sqlite
python -m trad3r order-writer-history runs/orders.sqlite
```

The other deterministic outcomes are `rejected` and `accept_then_timeout`. The
latter models acceptance followed by a lost acknowledgement and stores `unknown`.
It is a fault fixture, not a random network simulation.

All `at` values are explicit virtual-clock inputs for deterministic synthetic
tests. They are not a connected service clock. Any later paper adapter must obtain
time from its reviewed runtime and cannot trust a request to backdate authority.

On process recovery, the current fenced owner must run the explicit recovery
operation before a replacement owner can claim a higher epoch:

```sh
python -m trad3r order-writer-recover runs/orders.sqlite examples/order-writer-recovery.json
```

Recovery never dispatches queued work. A committed `submitting` operation becomes
`unknown`, retains all resources and leaves the writer disarmed. Every recovery,
including one with no in-flight command, also invalidates reconciliation. A new
claim therefore requires a complete [P4.4 snapshot](order-reconciliation.md), then
names the current epoch and receives the next epoch. An old owner or epoch cannot
mark or commit a result. There is no automatic lease expiry or unfenced takeover.

## Durable boundary

The version-3 database contains four related projections. Fresh version-4 stores
retain them and add the separately replayed reducing-allocation projection:

- the account audit retains admissions, attempts, reservations, identity
  incidents and locally proved expiry releases;
- the writer event log retains claims, command markers, results, recovery and
  writer identity incidents in its own contiguous sequence;
- writer and submission rows are reconstructed and compared with that event log
  on every operation.
- reconciliation inbox, event log and projection retain cumulative external
  evidence and atomically audited account adjustments.

Each submission binds one immutable operation ID, admitted intent,
`client_order_id`, canonical command and digest, writer owner and epoch. Exact
redelivery returns the stored state with `should_call_adapter: false`. Changed
reuse of an operation, or a second operation for the same intent, records a
blocking `writer_identity_conflict` and disarms the writer.

Before the marker transaction, the writer rechecks ownership, epoch, the caller's
expected account version, the proposal's policy and ledger/risk/evidence versions,
halts, unresolved account incidents, immutable expiry and the age of its bound
quote and FX evidence. A stale version or malformed request writes nothing. If the
authority is already expired, the same transaction records local cancellation,
releases the unused reservation and creates a never-dispatched operation tombstone.
The consumed entry attempt remains consumed, and the authority cannot be renewed.

For a valid operation the sequence is:

1. commit `submission_marked` with state `submitting`;
2. call the deterministic synthetic adapter outside the database transaction;
3. commit `acknowledged`, `rejected` or `unknown` as a separate event.

An acknowledged order keeps its reservation because executions, fees, cash and
positions are not yet reconciled. A definitive synthetic rejection also keeps the
reservation and disarms the writer pending P4.4's complete account evidence. An
uncertain result is always `unknown`. No terminal label by itself releases
financial resources.

If step 1 fails, no adapter call occurs. If step 3 fails after acceptance, the
durable state remains `submitting`; exact retry still does not call the adapter.
Explicit recovery converts it to `unknown`. This deliberately prefers blocked
capacity over a duplicate economic order.

## Compatibility and remaining scope

`order-init` continues to create store version 3. `order-v4-init` explicitly creates
a fresh version-4 store with the same admission, writer and reconciliation history
plus reducing allocations. Version-1 admission, version-2 writer and version-3
reconciliation databases remain readable by their implemented subsets, but only
fresh v4 stores accept reducing allocations. No in-place financial-state migration
is attempted.

P4.3 also does not add same-intent reauthorisation after bound account, ledger,
risk or evidence versions change. Such a change fails without a marker or adapter
call. A future account-state update design must record fresh authority without an
extra attempt and without extending the original expiry before that lifecycle path
can be enabled.

Deterministic tests cover concurrent claims, epoch fencing, exact retries,
identity conflicts, marker and result commit failure, acceptance with lost
acknowledgement, explicit restart recovery, stale account state, expiry release
and resource retention. They use invented data and no network.

P4.4 now implements synthetic startup and disconnect reconciliation against
complete supplied orders, executions, positions, USD cash, commissions and an
empty settlement set. It resolves `submitting`, `unknown`, acknowledged and rejected
states only from correlated evidence. P4.5 owns position-reducing cancellation,
sell settlement and protection incidents. Connected paper and live execution
remain behind their owner gates.
