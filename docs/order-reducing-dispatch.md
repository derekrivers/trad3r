# Synthetic reducing-order dispatch

P4.5 package E, delivered in [PR #40](https://github.com/derekrivers/trad3r/pull/40),
adds the only runtime path that can turn a reserved v4 sell allocation into a
synthetic broker command. It has no network adapter and cannot enable live trading.

Each request binds one immutable allocation and operation identity to the current
account, entry reconciliation, reducing reconciliation, writer, allocation,
cancellation and dispatch versions. It also binds the writer owner and fencing
epoch, decision and expiry, order type and exact price. Reducing exits are day
limit orders. Protective allocations are day stop orders. Market orders and
fallback orders are outside this package.

The dispatch journal commits `submitting` and disarms the writer before calling
the injected synthetic adapter. Acknowledgement retains the full allocated sell
remainder until complete cumulative evidence correlates the broker identity.
A lost response remains unknown and retains the same bound. Exact replay returns
the retained operation without another call; changed reuse latches an identity
incident. A crash or failed result commit therefore leaves a durable marker and
cannot cause a blind retry.

A definitive synthetic rejection proves that no order was created and releases
that allocation for a newly fenced allocation. The historical allocation remains
in its journal. Working, filled or cancelled outcomes come only from complete
cumulative order evidence. An order appearing without a dispatch marker, or with
a broker identity that disagrees with an acknowledgement, is a durable
reconciliation incident. Empty open-order evidence cannot resolve an unknown
submission or free its possible remainder.

The implementation revalidates current holdings, cumulative commitments, fee
allocation, evidence freshness, session, storage health and every bound version
inside the same database transaction as the marker. Entry pauses and risk halts
do not create sell capacity and are never cleared by dispatch. Fourteen deterministic
tests cover limit and stop commands, duplicate/concurrent calls, rejection,
lost acknowledgement, empty inventory, broker correlation, stale fencing,
rollback and journal corruption.

Package F still owns durable pause, desired action, protection incidents and
evidence-bound owner recovery. Package G owns the integrated full-lifecycle fault
rehearsal. Databases created by earlier v4 packages do not gain these tables in
place; they fail closed and require a newly initialized synthetic v4 store.
Connected paper and every live broker path remain disabled.
