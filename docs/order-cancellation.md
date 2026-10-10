# Fenced synthetic cancellation

P4.5 package D, delivered in [PR #39](https://github.com/derekrivers/trad3r/pull/39),
implements cancellation as a durable operation on one known order in
a fresh version-4 synthetic order store. It has no broker, network, paper-account or
live endpoint. `live_trading_enabled` remains false.

The cancellation request binds an immutable operation ID, exact client and order
IDs, account/environment, writer owner and epoch, decision and expiry times, and
the current account, entry-reconciliation, reducing-reconciliation, writer,
allocation and cancellation versions. Authority lasts at most 60 seconds in the
account's existing reviewed session. Cancellation does not require a fresh quote,
FX observation or free sell quantity because it cannot create an order.

`order-cancel-synthetic` first commits `cancel_pending` and disarms the shared
writer in one SQLite transaction. Only that committed marker permits the synthetic
adapter call. An exact retry returns the retained operation and never calls the
adapter again. Changed operation identity or a second unresolved cancellation for
the same target records a durable incident and keeps the writer disarmed.

Adapter outcomes are deliberately narrower than order truth:

| Adapter result | Cancellation state | Resource effect |
| --- | --- | --- |
| Accepted with receipt | `accepted` | None; cumulative order evidence is still required |
| Rejected with confirmed working status | `rejected_working` | None; the original working order remains authoritative |
| Bare denial or lost response | `unknown` | None; reconciliation remains mandatory |

An accepted response never changes order quantity, cash, holdings, fees, risk
reservations or settlement. Complete P4.4 or package-C evidence resolves the
operation: `cancelled` becomes `confirmed_cancelled`, `filled` becomes
`moot_filled`, and newer confirmed `working` evidence resolves an unknown result as
`rejected_working`. Partial fills remain cumulative account facts and retain the
entire possible remainder until terminal evidence. A response arriving after the
order filled is retained without regressing the order.

The cancellation journal stores every request, command digest, adapter response,
incident, transition and writer-event digest. Reads replay contiguous events and
verify state projection, SQL identity columns, writer fencing, and the exact
retained entry or reducing reconciliation snapshot used as terminal evidence.
Journal or projection damage therefore blocks account, writer and allocation
reads. Result-commit failure leaves the durable marker intact, so restart and exact
retry cannot issue a blind second cancellation.

The CLI also exposes `order-cancel-status` and `order-cancel-history`. These are
read-only. Package D does not add reducing-order submission, stop replacement,
incident recovery, settlement release or a new entry episode; those remain in the
ordered P4.5 packages E–G.

Twelve deterministic tests cover accepted, rejected, denied and lost responses;
partial entry and sell fills; fill-before-response; confirmed cancellation;
duplicates and concurrent exact requests; identity conflicts; stale fencing and
expiry; restart and result-write failure; replay corruption; CLI safety; and v3
isolation.
