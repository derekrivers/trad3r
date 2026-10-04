# Bounded research scenarios with approved rollover

The owner approved [option B](period-transition-proposal.md) on 2026-10-04.
`offline-unhalted-period-rollover-v1` applies only to isolated in-memory historical
research runs. It cannot read, alter or renew a durable risk account, connect to a
broker or operate a paper/live account. Every output keeps live trading disabled.

```sh
python -m trad3r simulate-research-series runs/research-scenarios.json
```

The input is the existing [series contract](series.md) plus a required inclusive
window: `"window": {"start": "2026-09-04", "end": "2026-09-09"}` alongside
`sessions`. Also require a versioned `strategy_id` such as
`"synthetic-scenarios-v1"` (1–128 ASCII letters, digits, hyphens, underscores or
dots). This supplied identifier is an audit declaration, not verification that a
particular generator produced the signals. Only the first session may provide
funding. All session dates must lie
within the supported window, be unique and advance chronologically. Costs, FX
observations and supplied signals remain explicit. The fixed signal contract is
identified as `supplied-signals-v1`; these scenarios are not a fitted strategy.

The result hashes the parsed bars, scenarios, strategy identifier, window and policy together as
`inputs_sha256`. The CLI also records the exact scenario-file hash and, when used,
archive hash. A changed cost, bar or window changes the input identity. Missing
scheduled dates are listed in `missing_sessions`; no valuations or equity path are
invented for those dates. Short intraday slices retain their truncation flags.
Results are engineering scenarios, not qualified strategy-performance evidence.

## Rollover order

The first session funds one £1,000 account. Later sessions keep all cash, pending
settlements and P&L, and release only settlement-eligible proceeds. Before considering
a rollover, the engine requires a flat position and values the account using fresh
FX at the first supplied bar. There is no pending-order queue in this synchronous
simulator; this must be revisited before adding asynchronous orders.

Assess that fresh mark against **old** daily/weekly baselines and the permanent
cumulative £300 limit. An existing or newly triggered halt prevents rollover and
all later entries in that run. A recovering valuation or a later week cannot clear
any daily, weekly or overall halt.

If no halt exists, use the current full mark as the new daily baseline. Preserve
the weekly mark within the same Monday-based New York week; renew it only on a
new week. Keep original funding and cumulative flows as the overall-loss basis.
The £10 daily, £25 weekly and £3 planned all-in trade limits are unchanged.

## Audit and failure semantics

`transitions` records each applied or blocked new-session attempt: policy ID,
timestamp, mark, old/new baselines and periods, pre-rollover assessment and the
associated ledger valuation event ID. A blocked attempt preserves both baselines.
Per-session outputs expose their actual starting marks and cumulative account
state. Do not sum per-session cumulative P&L.

The one ledger journal reconstructs cash, positions, settlement and final equity.
The transition journal records risk-baseline changes separately; replaying only
ledger events does not reconstruct those baselines. All output is deterministic
for identical inputs. Invalid later data produces no partial success report, and
no caller-supplied database/state object can be passed into this public run API.

This is a new research run, not resumption of a previously halted account.
Repeatedly starting a fresh experiment cannot be used to hide a prior halt when
presenting continuous-account results. The existing `simulate-series` contract and
SQLite risk store still block new-period entries; neither inherits this exception.
