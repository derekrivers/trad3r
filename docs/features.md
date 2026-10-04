# Completed-minute descriptive features

```sh
python -m trad3r features data/trad3r_sample.zip --journal runs/features.jsonl
```

The CLI requires complete scheduled minute coverage for all declared sessions and
symbols. It emits one `features_closed` JSONL event per atomic completed-minute
batch, with schema `completed-minute-features-v1`, availability time, session and
canonical symbol rows. The summary records source hash, journal hash, feature
schema and calendar version. Output files are created exclusively, after input
and feature computation succeed. Licensed feature data must stay outside git.

## Formula contract

All calculations use Decimal. Returns are fractions, not percentages. Each row
is computed only from that symbol's current and earlier completed session bars.

| Field | Definition and availability |
| --- | --- |
| bars_seen / close | Session count and latest completed close |
| return_1m | Current close / previous close − 1; null on the first minute |
| return_5m | Current close / close five minutes earlier − 1; needs six bars |
| sma_5 | Mean of the latest five closes, including current; needs five bars |
| prior_volume_mean_20 | Mean volume of the preceding twenty bars, excluding current |
| volume_ratio_20 | Current volume / prior_volume_mean_20; null during warmup or if denominator is zero |
| cumulative_volume | Sum of observed session volume through the current bar |
| ohlc_vwap_proxy | Sum of ((high + low + close)/3 × volume) / cumulative_volume; null when total volume is zero |
| opening_range_high / low | Maximum high / minimum low over the first thirty session minutes; null until complete, then frozen |
| opening_range_complete | True only from completion of the 09:59 New York bar at 10:00 |

The OHLC-based volume-weighted value is a **proxy**, not transaction-level VWAP.
There is no spread, order-book, liquidity score, profitability probability or
classifier output. Nulls are explicit unavailable values, never zero-filled.
The schema is a descriptive engineering baseline, not a validated feature selection.

## Causality and session handling

The engine must begin at 09:30 New York and consume contiguous complete batches.
It rejects duplicate/backwards timestamps, missing minutes and incomplete symbol
membership. Updates commit across all symbols together; rejection cannot advance
the engine. Changing future valid bars or appending a valid suffix cannot alter
earlier feature values. Tests verify that property and opening-range availability.

Features reset at each new session. This reset concerns statistical windows only;
it does not reset an account, loss budget or risk latch. Overnight returns and
cross-session rolling features are deliberately absent. Missing sessions are not
fabricated, and the fixed declared universe is not proven point-in-time unbiased.

These timestamps describe when a historical bar completes, not when a live vendor
delivered it or when a later correction became known. Revision history, authentic
delivery latency and corporate-action research remain necessary before strategy
validation. The in-memory API permits a contiguous session prefix for streaming
tests; the archive CLI requires the declared complete session grid.

## Before training or trading

There are no labels, fitted transforms, learned parameters, trade signals or
orders. A later research protocol must freeze a hypothesis and feature schema,
define net-cost labels separately, reserve chronological validation/test periods,
and fit preprocessing only on training data. These features do not establish that
a strategy has an edge and cannot bypass the independent risk gates.
