# Prepare an archive-backed engineering scenario

`prepare-baseline` connects the stock/FX [acquisition archive](acquisition.md) to
the existing frozen baseline runner. It validates and selects inputs without
running the strategy or inspecting performance. It cannot qualify data, choose
an investment, establish an untouched holdout or authorise trading.

## Local workflow

After acquiring a stock/FX archive, supply a labelled JSON assumptions file using
the structure in `examples/research-assumptions.json`. That example invents a
£400-to-$500 conversion and fixed fees/slippage solely for engineering tests.
It is not a recommended currency conversion or an actual broker quotation.
Use a private file in `data/` to record the intended assumptions before evaluation.

```sh
python -m trad3r prepare-baseline data/history-with-fx.zip data/assumptions.json --symbol AAPL --start 2026-09-04 --end 2026-10-02 --output runs/prepared-baseline.json
python -m trad3r baseline-backtest runs/prepared-baseline.json --archive data/history-with-fx.zip
```

Symbol selection is explicit and fixed across the run. The CLI does not rank the
downloaded stocks, select a winner or tune a strategy. The preparation output is
private research data: it contains selected licensed FX observations. Keep it in
ignored `runs/`, and do not commit or redistribute it.

## Required assumptions

The schema is `fixed-cost-research-assumptions-v1`, with exactly `schema`, `label`,
`funding` and `costs`. Supply a nonempty label up to 200 characters describing the
assumptions' provenance/status. Funding contains the GBP `amount`, USD `received`
and GBP `fee_gbp`; the existing ledger validates that conversion against the one
£1,000 initial account. There is no inferred conversion rate or later replenishment.
Only the first session receives funding.

Costs explicitly contain nonnegative `entry_fee_usd`, `exit_fee_usd` and
`slippage_usd_per_share`, used uniformly across the requested window. This simple
model does not calculate commissions from notional, volume tiers, routing or dated
regulatory schedules. It must not be described as a qualified IBKR fee model.
Preparation rejects extra settings, including any strategy override. Scenario
settlement dates come from the existing conservative reviewed calendar; unsupported
dates fail, and the runner continues to apply its explicit simulated settlement
events and cash-availability policy.

## Stock and FX checks

The archive is read once into a bounded byte snapshot. Inventory, payload digests,
stock parsing, FX parsing and source hashing all use that snapshot. Every declared
stock grid must be complete, and the requested symbol must cover all scheduled
sessions in the explicit window. Missing sessions are not skipped.

FX records require the exact `historical-completed-bar-proxy-v1` schema, positive
finite values, unique chronological UTC timestamps and whole-minute starts.
Availability must equal minute start plus one minute, and GBP per USD must equal
the 28-digit decimal inverse of the declared GBP/USD close. Wrong direction,
retimestamped opening values and duplicate records fail validation.

For each simulated valuation boundary from 09:30 through 12:00 New York, select
the latest observation at or before that instant. Its age must be at most 60
seconds, matching the simulator's existing rule. Preserve its actual timestamp;
do not backfill from a future minute or relabel an old observation as fresh.
A single absent FX minute can be covered by a 60-second-old observation; longer
gaps fail. Preparation reports the maximum selected age and observation count.
These checks establish internal timing consistency, not real delivery latency,
quote availability, spread or executable currency conversion prices.

## Output identity and execution

The output includes exact archive and assumptions-file SHA-256 values, the schema,
model and assumptions label. Identical bytes and inputs produce identical scenario
bytes. Validation and complete serialization finish before exclusive atomic output
publication; existing files are preserved. The same hard-link filesystem requirement
as acquisition applies. There is no partial success result on invalid inputs.

Prepared scenarios require `baseline-backtest --archive` with the matching archive
SHA-256. Another archive, even with identical stock bars but different FX or metadata,
fails before simulation. The result retains preparation metadata, scenario identity,
the full account journal and same-cash comparison. The ordinary manually supplied
scenario format remains supported. Hashes identify inputs; they do not authenticate
the author or prevent someone deliberately editing a scenario and recomputing hashes.

The old 20-session stock-only engineering sample cannot supply this FX contract.
Acquire the combined archive when account access is available. Before credible
historical interpretation, complete the [research qualification and registration
steps](research-readiness.md); a prepared scenario remains `engineering_scenario_only`.
