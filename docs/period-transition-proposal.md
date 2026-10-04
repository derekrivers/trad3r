# Proposed offline period-transition workflow

Status: **option B explicitly approved by the owner on 2026-10-04 and implemented
as `offline-unhalted-period-rollover-v1` in isolated research scenarios**.
Option A remains an unimplemented design. Approval grants no halt-reset authority.

The current account freezes its initial session/week baselines and blocks entries
on later dates. `AGENTS.md` prohibits AI halt resets and automatic loss-budget
renewal except the approved option B scope. The risk/series contracts required an owner-reviewed transition
workflow. General authority to build and merge code does not establish this
financial-state rule; this document makes the decision concrete.

## Option A: individually reviewed transitions

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

Approval of option A would permit implementing this explicit, non-halted,
offline-only transition design. It would not approve individual transition records
or any future halt-reset mechanism.

## Option B: bounded automatic rollover in isolated historical backtests

Approved for practical offline research on 2026-10-04 after the owner explicitly
accepted the proposed scope. This is a narrow exception to the `AGENTS.md`
prohibition on automatic loss-budget renewal. General development authority alone
was not used to infer this financial-state rule.

Approve a deterministic historical run policy with these precise constraints:

1. Apply only inside an isolated in-memory backtest with explicit start/end dates,
   source hashes, strategy version and a recorded policy identifier. No broker
   connection, durable risk-database mutation, paper/live-account operation or
   clock-driven daily task. A new run is a research experiment, never a way to
   resume or conceal a halt in an existing account.
2. Fund £1,000 once. Carry the same ledger, cumulative flows, pending settlements
   and all risk latches through all supplied sessions. Record gaps; invent no
   observations or skipped-day equity. Use the existing scheduled settlement and
   conservative research cash-release rules.
3. At each new scheduled session, require flat positions, no pending simulated
   orders and a valid fresh valuation. Assess that valuation against the existing
   baselines **before** any rollover, so overnight FX or other observed losses
   cannot disappear into a fresh starting mark.
4. If any daily, weekly or overall halt is already present or newly triggered,
   do not roll over and do not permit further entries in that run. Continue
   accounting/valuation as appropriate. Price recovery, a new week and deposits
   cannot clear the halt. There is no automatic restart.
5. Otherwise set the new daily baseline to the current full mark. Preserve the
   weekly baseline within the same Monday-based New York week; change it only at
   a new week. Keep the £300 cumulative limit anchored to original funding and
   cumulative external flows, and keep the £10/£25/£3 limits unchanged.
6. Journal the valuation, old/new baselines, period IDs, policy ID and decision.
   Results must reconcile to the one continuous account. Missing inputs, unknown
   calendars or inconsistent state fail the run without partial success output.

The implementation requires the same preservation, breach, settlement,
chronology and replay tests listed above, plus tests proving that option B cannot
operate on a durable account or enable live trading. Synthetic inputs may test
the mechanics; qualified FX/cost/history inputs are still required for credible
strategy evaluation. This option grants no authority to clear any halt or change
the £300 maximum-loss policy.

The implementation is available through `simulate-research-series`; see
[the research rollover contract](research-series.md). The ordinary `simulate-series`
and durable risk-store paths retain their existing period blocks. The
[`baseline-backtest`](baseline-backtest.md) command generates the frozen hypothesis
over that same research policy. Option A remains the alternative design for individual reviews.
