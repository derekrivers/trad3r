# Proposed offline period-transition workflow

Status: **design for owner review; not implemented or approved**.

The current account freezes its initial session/week baselines and blocks entries
on later dates. `AGENTS.md` prohibits automatic loss-budget renewal and AI halt
resets. The existing risk/series contracts require an owner-reviewed transition
workflow. General authority to build and merge code does not establish this
financial-state rule; this document makes the decision concrete.

## Proposed behaviour

Allow an explicit, audited transition to a later scheduled exchange session for an
offline account only. Do not transition on a timer or merely because a new bar/date
arrives. Continue blocking live execution. A transition cannot clear **any**
existing daily, weekly or overall halt. Resuming a halted account is outside this
proposal; creating a new database or experiment to conceal its halt is prohibited.

| State | Proposed transition result |
| --- | --- |
| New session, same New York Monday-based week, no halt | New daily baseline from the reviewed current adjusted-equity mark; preserve weekly baseline |
| New session and new week, no halt | New daily and weekly baselines from that reviewed mark |
| Any existing halt or a new breach on the transition mark | Reject transition; preserve all baselines and latches |
| Duplicate/same/backwards date, unknown calendar, stale state or missing evidence | Reject without mutation |
| Position, pending order or unresolved reconciliation discrepancy | Reject; review/resolve first |

Initial £1,000 funding and the cumulative £300 loss calculation remain unchanged.
Retain cash, pending settlements, realised/unrealised account P&L, cumulative
deposits/withdrawals and event history. A new baseline uses the full current mark
(including cash flows); it does not credit a deposit as trading profit. Pending
sale proceeds remain unavailable until the existing settlement policy releases
them. No daily transition alters the weekly baseline within the same week.

## Review record and application

First record the fresh new-period mark through the normal durable risk-observation
route against the old baselines. Any breach must latch there, even if a later
transition is rejected. A transition must never be a way to skip observing a loss.
Then produce a read-only proposal for that recorded mark with account identity,
expected state version/hash, prior/new period identifiers, current equity and
flows, both old and proposed baselines, unchanged limits, reconciliation/flatness
evidence and the reason for transition. The owner must explicitly accept the
specific transition record. A CLI flag or an AI-written `approved: true` field is
not evidence of owner approval.

Apply the authorised record against the same expected state in one transaction.
Recheck the recorded assessment and unchanged mark against the existing baselines
and cumulative limit; reject if blocked. Do not accept a replacement mark through
the transition command. Commit the transition audit event and new baselines
together only if all checks pass. Reject duplicate
IDs, version changes and replayed approvals; preserve state on failure. Ledger and
risk evidence must refer to the same instant. Account/order reconciliation remains
an explicit dependency, not an inferred success from a missing position field.

For historical research, input marks and review records may refer to historical
times; they still need identity/provenance and cannot pretend to be current broker
evidence. Automating offline transitions across an entire date range would require
a separately explicit owner-approved policy change to the present prohibition on
automatic renewal. It is not included in this proposal.

## Required implementation tests after approval

- Same-week transition preserves weekly losses; new week changes only eligible
  period baselines; original capital/flows/overall loss basis never change.
- Existing halts and breaches caused by the transition mark cannot be cleared,
  including after price/FX recovery, deposits, restarts or a later week.
- Unsettled cash survives unchanged; positions, unknown order state or failed
  reconciliation prevent a transition.
- Stale versions, changed marks, duplicate review IDs and concurrent requests fail
  without partial updates; audit replay reconstructs the same state.
- Continuous research results reconcile to one ledger and never sum freshly
  funded daily simulations. No CLI route enables live trading.

The owner decision requested is approval of this explicit, non-halted,
offline-only transition design for implementation. Implementation authority would
not approve individual transition records or any future halt-reset mechanism.
