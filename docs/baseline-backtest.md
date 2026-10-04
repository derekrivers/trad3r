# Continuous frozen-baseline research

`baseline-backtest` generates `orb30-one-share-v1` candidates and passes them
through the [approved bounded research runner](research-series.md). It retains
one account across all supplied sessions, including costs, FX, settled/unsettled
cash, daily/weekly baselines and every triggered halt. There is no broker account
or live trading route. The hypothesis remains unvalidated.

## Run the synthetic engineering example

From the repository root:

```sh
mkdir -p runs
python -m examples.make_baseline_scenario > runs/synthetic-baseline.json
python -m trad3r baseline-backtest runs/synthetic-baseline.json
```

On Windows, create `runs` through Explorer or `mkdir runs` first. The generator
prints a two-day invented price pattern with constant assumed FX and costs. It is
a software demonstration, not historical performance or a broker fee quotation.

## Input contract

Use a `window` and `sessions` as in research scenarios, but omit `strategy_id` and
every `signals` field. This command fixes the strategy version and generates the
signals itself; it rejects overrides, even empty signal arrays. Every scheduled
session in the inclusive window must appear exactly once in order, and every
session must use the same preselected symbol. Automatic symbol rotation, ranking
and parameter optimisation are absent.

Supply contiguous minute bars beginning at the scheduled open and extending at
least through the noon flatten deadline. Inline synthetic prefixes ending before
noon are rejected here, unlike isolated `baseline-simulate` engineering scenarios.
An optional `--archive` supplies bars instead; archive coverage must be complete
for its declared grid, and the requested window must still include every session.
No missing session is silently treated as a no-trade day.

Costs and timestamped FX are mandatory in every session. Only the first session
may specify the initial conversion from the single £1,000 research account. No
prices, funding conversions, fee rates or FX rates are inferred from stock bars.

## Output and limits

The output identifies the strategy, feature schema, policy, window and exact input
hashes; per-session reports include all generated candidates, execution rejections,
actual entries/exits and account snapshots. No-candidate sessions remain visible.
The complete ledger replays to the final account report, and transition records
explain every eligible or blocked rollover. Cumulative session P&L must not be summed.

`research_status` remains `engineering_scenario_only`. A new bounded experiment
cannot be described as resumption of a halted account. Qualified economic inputs,
independent price checks and untouched chronological validation remain necessary;
running this command does not qualify data or establish profitability.
