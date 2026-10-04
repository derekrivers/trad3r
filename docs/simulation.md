# Single-session execution scenarios

```sh
python -m trad3r simulate examples/simulation.json
```

The synthetic example deliberately touches a stop and profit target in the same
minute. It records the stop, losing GBP 2.56 including the declared costs. This is
an arithmetic/execution test, not a strategy, recommendation or return forecast.

Each run starts an isolated GBP 1000 research account. It never reads, resets or
writes a durable risk database. Its results cannot resume an existing stopped
account. Loss latches and attempt counts are held for the entire simulated session;
the emitted ledger events reconstruct its accounting result.

## Inputs

The example defines one symbol/session, contiguous validated minute bars, explicit
funding conversion amounts, entry/exit USD fees, one-way adverse execution allowance,
timestamped GBP-per-USD FX observations, signals and a future settlement date.
All numeric assumptions use decimal strings except the historical OHLCV JSON
numbers. FX observations must be unique and chronological; only observations
available by the current event are used, and they expire after 60 seconds.

For private historical prices, omit `bars` from the scenario and run:

```sh
python -m trad3r simulate runs/scenario.json --archive data/trad3r_sample.zip
```

The CLI verifies the archive and selects only its raw-price symbol/session. Output
includes the exact scenario-file hash and archive hash. Supply appropriately
timestamped FX separately; the program does not invent current FX observations.
The example's flat FX is a synthetic assumption, not historical FX data. Keep
historical scenarios and outputs under ignored `runs/`; do not publish vendor data.

Signals have unique `id`, completed-bar availability timestamp `at`, whole-share
`quantity`, `stop`, and `target`. They must be chronological and reference a bar
in the supplied pre-noon slice. Supplying hindsight-selected signals is possible;
this engine alone cannot validate a strategy or prevent caller-side lookahead.

## Event order and fill assumptions

1. At each bar open, mark the account using that open and available FX. Existing
   stop/target opening gaps are processed first. Otherwise a latched risk halt
   closes at the opening price less the adverse execution allowance.
2. A signal can attempt entry only at a bar opening **strictly after** its producing
   bar's availability: a 10:00 signal first attempts at 10:01. It cannot fill on
   its source bar or at the same instant that bar becomes available.
3. Recheck risk using the actual candidate opening price, fees and allowance. Reject
   brackets invalidated by a gap. Every processed request consumes an attempt,
   including rejection; the fourth and later cannot enter. One position only.
4. Buys pay open plus the allowance. An opening stop gap exits at open minus the
   allowance; an opening target gap receives no improvement over target minus the
   allowance. If neither gap resolves the trade and both intrabar levels touch,
   take the stop. All exits deduct their explicit fee.
5. Intrabar outcomes are attributed to bar completion because OHLC cannot identify
   their actual time. Their GBP accounting uses FX available then. A profit target
   is modelled as a market-exit trigger with adverse costs, **not a limit order**.
6. Observe closing equity and latch losses. A halt first seen at a close exits on
   the following open, never retroactively at the just-observed close.
7. Pre-scheduled liquidation uses the 11:59 bar close at noon New York time, less
   allowance. A shorter dataset liquidates at its final close and is explicitly
   marked `truncated_session`. Signals without a later eligible bar expire.

The entry window is 10:00 to strictly before 11:30 New York time. No entry gate
blocks an exit. Pending sale proceeds stay unsettled for this one-session run.
Stop gaps can exceed the planned GBP 3 loss; tests intentionally demonstrate that.

## What this does not establish

These rules are adverse in the specified cost and ambiguity cases, but they are
not a universally conservative model of actual markets. There is no queue, volume
participation, bid/ask feed, trading-halt, partial-fill or liquidity model. Supplied
fees, FX and allowance must be calibrated before performance evaluation. A cost
assumption producing a nonpositive fill price causes an error, not a fabricated fill.

Exchange holidays, early closes and verified settlement calendars remain open.
Multi-symbol event batches, multi-session period transitions, strategies and
out-of-sample validation are not implemented. Isolated session outputs must not
be added together as though each received a fresh real loss allowance.
All output explicitly disables live trading.
