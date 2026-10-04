# Historical sample contract

The reader accepts the version-1 ZIP produced by the project's Massive sample
downloader: a manifest, its listed payload files and SYMBOL_raw_prices_rth.jsonl
series. File sizes and SHA-256 digests are verified before replay. Archives are
read directly without extraction. Version 0.1 is bounded to 50 MiB compressed,
100 MiB expanded and 1,000 members; this is a sample reader, not a bulk archive engine.

Each row includes symbol, UTC minute-start timestamp, session_date, USD currency,
o/h/l/c and volume. JSON decimals are parsed as Decimal; fractional volumes are
valid. Ordering, duplicates, finite values and OHLC constraints are checked.
The timestamp must fit its scheduled New York regular session under the bounded
[2026 exchange calendar](calendar.md), including holidays and early closes.
Daylight saving is handled by IANA timezone data; unknown years fail closed.
The manifest is an integrity inventory, not an authenticated vendor signature.
Unscheduled closures and source provenance still need independent checks. The
reader reports scheduled minute-grid coverage for every declared symbol/session.

## Coverage and atomic completed batches

Every validation summary includes expected/observed/missing minute counts, a
`complete` flag, and at most ten missing UTC start-time examples per symbol/session.
The grid follows the versioned exchange calendar: 390 regular minutes or 210 on
the supported early closes. Entire declared sessions without bars are visible.
Missing minutes are never filled, interpolated or assigned invented volume.

```sh
python -m trad3r validate data/trad3r_sample.zip --require-complete
python -m trad3r replay data/trad3r_sample.zip --require-complete --batches --journal runs/batches.jsonl
```

Default validation still permits sparse archives for inspection; strict mode
rejects any missing minute before creating a replay journal. A missing aggregate
can reflect no eligible trades, a halt or a feed gap; this check does not establish
which. Completeness is relative to the **declared** dates and symbols: omitted
manifest sessions, survivorship bias and the suitability of the universe remain
separate research checks. Complete bars do not prove liquidity or price accuracy.

`--batches` emits one `bar_batch_closed` event per observed availability timestamp,
containing every declared symbol exactly once, sorted by symbol. All member bars
close at that timestamp; no member is individually exposed to a downstream
consumer before the whole batch. Missing/duplicate members fail before any output
file is created. A whole missing timestamp requires `--require-complete` to catch.
The batch layer makes no ranking or order decision and is not multi-symbol execution.

The default per-bar journal remains byte-compatible. Replay summaries now identify
`completed_bars_v1` or `completed_batches_v1` and the journal event count. Both
formats remain deterministic and refuse to overwrite existing output files.

## First sample evidence

Private archive: trad3r_sample_20261004T160256652430Z.zip.
SHA-256: eebd9e7454227356d9b7d1bcbe9e1518bcd18721fdf441a9179e19a3b534074b.
Coverage: 4 September through 2 October 2026; AAPL, MSFT, F; 20 regular sessions.
Each symbol has 7,800 raw-price regular-session minute bars without missing minutes.
The supplied adjusted copies are identical for this window. The archive passed
structural review; it is not evidence of a trading edge or an independently audited
minute feed. This repository deliberately contains none of its licensed prices.

Normalized bars start at 09:30 through 15:59 New York time. The last bar close is
not necessarily the official daily close. The raw payload retains the 16:00 bars;
do not append that entire minute as though it were only a closing-auction print.
This fixture does not exercise DST transitions, early closes or a known split.

Replay assumes a completed bar can be used at its end timestamp. Historical bars
may include later corrections; real delivery latency and revision modelling remain
open. A bar alone cannot determine bid/ask spread, execution queue, fill quality or
the order of a stop and target touched in the same minute.

## Next data work

Add a corporate-action case, an independent minute-level comparison and broader
history before strategy validation. Use raw historical prices for whole-share
quantity and cash calculations; keep adjustment metadata separate for features.
Do not round market volume to whole shares. Select chronological evaluation splits
and a point-in-time universe before tuning; current surviving stocks are biased.

Data is for the owner's licensed private research. Keep ZIP/JSONL downloads in
ignored data/ and generated journals in ignored runs/. Do not redistribute vendor
data, commit keys, or send licensed content to a classifier without permitted use.
