# Frozen opening-range hypothesis

Identifier: `orb30-one-share-v1`. Feature schema: `completed-minute-features-v1`.
This is an unvalidated experimental hypothesis, frozen before inspecting its
private-sample outcomes. It is not a tried-and-trusted income strategy. Changes
to these rules require a new identifier and a recorded research trial; do not
silently tune this version in response to results.

## Rules

- One explicitly selected symbol and session; no automatic universe ranking.
- Start with the 09:30 New York bar and require every following scheduled minute.
  The first 30 bars define the opening-range high and low, available at 10:00.
- Select the first positive-volume completed bar whose close is strictly above
  the frozen range high and whose immediately previous close was at or below it.
  No trigger is possible inside the opening range itself.
- Signal availability must leave a full minute before the 11:30 entry cutoff.
  The last permissible signal is available at 11:28 for a possible 11:29 fill.
- Quantity is one whole share. Stop is the opening-range low. Target is signal
  close plus twice the difference between signal close and stop. This is a price
  reference calculation, not a claim of a net 2:1 realised reward/risk ratio.
- Emit at most one candidate, even if subsequent execution rejects it. A zero
  volume crossing does not create a deferred trigger while price stays above the
  range; a later fresh crossing may qualify.

No learned parameters, probability threshold, optimisation, shorting or leverage.
The existing simulator independently rechecks the delayed opening price, bracket,
settled cash, exposure, costs, FX freshness and remaining risk headroom. It applies
the same conservative exits and noon flattening as supplied scenarios. There is
no guarantee of a fill or of limiting realised losses to planned risk.

## Commands

```sh
python -m trad3r strategy-signals data/trad3r_sample.zip --symbol AAPL --session 2026-09-04
python -m trad3r baseline-simulate runs/scenario.json --archive data/trad3r_sample.zip
```

Use the [simulation scenario contract](simulation.md), omitting `signals` entirely.
Supply the selected symbol/session, funding conversion, explicit execution costs
and timestamped FX observations; none are inferred from historical stock bars.
`signals`, even an empty array, is rejected so a caller cannot override this
hypothesis. Archive commands require complete coverage of the declared grid.
Inline synthetic bars can be a contiguous opening prefix for engineering tests;
the result flags truncation and flattens at end of data if noon is unavailable.

The report identifies the strategy, feature schema, input hashes and generated
candidates. Results remain `engineering_scenario_only`; the command has no option
to label them validated. Do not publish licensed candidates, prices or features
in the public repository. `strategy-signals` does not test affordability or risk.

## Research boundary

One isolated run starts a fresh research account. Repeating isolated runs and
summing their P&L is not an account backtest: that would bypass loss latches,
settlement and cash constraints. `simulate-series` preserves account continuity
but blocks new-period entries pending the owner-reviewed transition workflow.
This version therefore does not supply a multi-day strategy backtest.

The existing 20 inspected sessions remain engineering data. Credible evaluation
still needs a frozen chronological protocol, untouched history, qualified FX and
execution-cost inputs, corporate-action checks and review of period transitions.
Only after that evaluation should a classifier be considered in shadow mode.
