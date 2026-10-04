# First historical engineering run plan — 4 October 2026

This plan is recorded before running or inspecting historical strategy outcomes.
Its purpose is to exercise the complete research pipeline, not to qualify an edge
or choose a winning configuration. The dates are already-inspected engineering
data, not an untouched holdout. All three cases must be registered before any runs.

## Fixed inputs and behaviour

- Source: the combined private archive identified in `research-readiness.md`,
  SHA-256 `6ba4e7fca0e6b875997d6a7ac81ede3f2356dedbb72f1ead73edce80dbc24f8a`.
- Window: 2026-09-04 through 2026-10-02, all 20 scheduled sessions.
- Symbol: AAPL only, preselected before outcomes. No MSFT/F ranking or selection.
- Strategy: `orb30-one-share-v1`; frozen parameters, one share, no classifier.
- One £1,000 account per explicitly separate counterfactual scenario, with the
  approved isolated-backtest rollover policy. Never concatenate the scenarios.
- Risk limits remain £300 cumulative, £10 session, £25 weekly and £3 planned
  all-in trade risk, with £500 exposure and all existing entry/time/settlement rules.
- No halt resets, signal overrides, risk relaxation or subsequent parameter tuning
  within this registered set. Rejections and no-candidate sessions remain visible.

## Initial currency assumption

Each case uses the same single £400-to-USD conversion at the first session opening,
leaving £600 in GBP before conversion effects. The hypothetical received USD is
`floor_to_cent(400 / first_available_GBP_per_USD * 0.9997)`. The rate is the completed
historical minute already available at the opening; never use that opening minute's
future close. The 0.03% haircut is an explicit conversion-cost assumption, and no
separate GBP fee is charged in the scenario. Record the actual computed amount and
source-rate convention in the private run notes before registration.

This is a hypothetical conversion, not an actual broker execution. The same-cash
reference receives exactly the same conversion and historical FX observations.

## Predeclared fixed cost cases

| Experiment ID | Entry fee USD | Exit fee USD | Adverse slippage USD/share on each fill |
| --- | ---: | ---: | ---: |
| aapl-engineering-base-v1 | 1.00 | 1.02 | 0.05 |
| aapl-engineering-stress-v1 | 1.25 | 1.27 | 0.10 |
| aapl-engineering-severe-v1 | 1.50 | 1.52 | 0.20 |

The base charge is a fixed-commission-like engineering proxy with a two-cent exit
allowance; the other two cases deliberately increase assumed friction. These are
chosen stress assumptions, not a qualified dated broker schedule, bid/ask model or
guaranteed upper bound on costs. Published schedules and their limitations are
linked in `acquisition.md`. No stock selection or parameter changes may follow from
choosing whichever of these counterfactual runs looks best.

## Checks and reporting

Require registered code/data/assumption identities, a complete session inventory,
reconciled baseline and reference ledgers, one initial funding per account, preserved
halts, and inspectable result bundles. Report all cases, including failures, zero
fills and adverse outcomes. Compare net account P&L with the same-cash reference;
disclose cash FX effects, realised trade P&L, fees, candidates/rejections, observed
drawdown and halt reasons. A positive account change alone is not a profitable
trading strategy. No numeric profitability acceptance criterion is set for this
engineering exercise, and it cannot pass the project into paper or live trading.
