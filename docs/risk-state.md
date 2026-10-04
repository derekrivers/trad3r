# Durable offline risk observations

The SQLite risk store preserves the agreed policy, starting marks, latest mark,
halt reasons and observation history between processes. It accepts observations;
it does not submit, authorise or cancel orders. `blocked: false` means only that
these recorded observations have not triggered a block. It is not permission to
trade, and does not prove the latest observation is current in the real world.

## Synthetic walkthrough

From the repository root, using a new, local database:

```sh
mkdir runs
python -m trad3r risk-init runs/risk.sqlite --at 2026-09-04T13:30:00Z
python -m trad3r ledger examples/ledger.json > runs/valuation.json
python -m trad3r risk-record runs/risk.sqlite runs/valuation.json --ledger-report --event-id ledger-1 --expected-version 0
python -m trad3r risk-record runs/risk.sqlite examples/risk-loss.json --expected-version 1
python -m trad3r risk-status runs/risk.sqlite
python -m trad3r risk-history runs/risk.sqlite
```

The second observation sets synthetic equity to GBP 700 and latches the overall,
daily and weekly stops. Restarting the CLI, recovering prices or depositing funds
cannot clear those latches. The initial database represents a new GBP 1000 research
account; it cannot import an existing live account. Initialisation refuses an
existing path. Never create a fresh database to resume a stopped research account.

Raw observations contain `id`, UTC `at`, and `mark` with all three fields: `equity`,
`deposits`, `withdrawals`. Values are GBP decimal strings; cash flows are cumulative
since initial funding. Ledger imports use net equity and cash flows, not realised
trade P&L. Every observation must be newer than the previous one, use a new ID, and
provide the current `version` from status. A duplicate is rejected rather than
returning a potentially obsolete earlier assessment; inspect current status before
retrying an uncertain request.

## Durability and failures

A SQLite immediate transaction serialises writes. Audit insertion and state update
commit together with FULL synchronous mode. Version checks prevent two callers
from overwriting the same version. A missing, corrupt, incompatible or mismatched
audit/state database fails closed: the command prints an error and exits 2 without
a success report. It never recreates a database during read/record operations.
Use a local filesystem, not a network share. SQLite durability relies on the
operating system and storage honouring flushes. Keep backups before real use.
Every read and append reconstructs the full ordered observation history: contiguous
versions, IDs, timestamps, cumulative flows, computed assessments and retained
latches. Each historical result and the final state must match the reconstruction.
This catches older audit damage even when the latest snapshot still agrees with
the latest row. An empty history must retain the original £1,000 mark and period.

The consistency checks detect disagreement, not a coherently rewritten whole
database by someone with file access. V1 stores the initial period but does not
retain a separate immutable funding timestamp after the first observation; replay
can check that first observation against the initial date, not the lost original
intraday timestamp. Appending observations still checks strictly newer timestamps.
No automatic repair or migration is provided. Existing consistent v1 stores remain
compatible. Verification is linear in history length on every operation; a later
larger-volume store needs reviewed checkpointing rather than skipping old entries.

Successful diagnostic commands return 0 even when halted; consumers must inspect
`blocked` and `blocked_reasons`. All results explicitly disable live trading.

## Period transitions remain blocked

Initial session and Monday-based week identifiers use New York dates. This is not
an exchange-holiday calendar. Crossing a date/week boundary adds
`period_review_required`; observations can still be stored and overall losses
still latch. Baselines are preserved, so the diagnostic daily/weekly fields then
mean P&L since the displayed original baseline, not a newly opened trading period.
There is no reset or rollover command. An owner-reviewed period-transition workflow
is a later increment; the system must not renew a loss budget on a timer.

Remaining controls include mark freshness, order admission, per-trade/exposure/entry
limits, broker reconciliation and flattening. Durable latches alone cannot enforce
those controls. The in-memory ledger still reconstructs from its supplied event
file; recording risk does not atomically persist ledger fills or orders.
