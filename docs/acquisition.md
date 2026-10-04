# Local historical acquisition

The separate `python -m trad3r.acquire` command downloads research inputs through
read-only Massive REST requests. The normal `trad3r` commands remain offline.
No broker account is needed. Downloading is explicit; without `--download`, the
command only prints a request plan and does not read credentials or create files.

## Cost and access check — 4 October 2026

Massive publishes Stocks Basic at $0/month, including historical minute aggregates,
two years of history, end-of-day availability and five calls per minute. Currencies
Basic also advertises $0/month, two years, minute aggregates and five calls per
minute. Check that the existing account has both entitlements; stock access does
not establish currency access. These historical inputs should not require a paid
upgrade under the published Basic plans. Actual account access has not been tested.
The tool cannot subscribe, upgrade or place orders. Stop on an entitlement error.

Sources: [Stocks pricing](https://massive.com/pricing),
[Currencies pricing](https://massive.com/currencies),
[stock aggregates](https://massive.com/docs/rest/stocks/aggregates/custom-bars),
[FX aggregates](https://massive.com/docs/rest/forex/aggregates/custom-bars).
Recheck the account's terms before downloading; this is private licensed research,
not permission to redistribute data or an assurance that every research need is free.

## First download

From the repository root, first inspect the plan:

```sh
python -m trad3r.acquire --start 2026-09-04 --end 2026-10-02 --symbols AAPL MSFT F --output data/history-with-fx.zip
```

Then run the identical command with `--download`:

```sh
python -m trad3r.acquire --start 2026-09-04 --end 2026-10-02 --symbols AAPL MSFT F --output data/history-with-fx.zip --download
python -m trad3r validate data/history-with-fx.zip --require-complete
python -m trad3r research-audit data/history-with-fx.zip --start 2026-09-04 --end 2026-10-02
```

Enter the API key at the hidden local prompt. Alternatively use a locally managed
`MASSIVE_API_KEY` environment variable. Do not paste it in chat, put it in command
arguments, commit it, or include it in an uploaded file. If secure terminal entry
is unavailable, the prompt fails instead of echoing the key. The command does not
load `.env` automatically. The existing inspected window is an engineering fixture,
not untouched validation data. Broader windows can be downloaded into separate
archives; do not inspect strategy outcomes before registering evaluation splits.

Authentication uses the documented
[Bearer header](https://massive.com/docs/rest/quickstart). Requests go only to the
fixed HTTPS API host. Redirects and pagination are refused, and error bodies are
never printed or stored. There are no automatic retries. API responses are bounded
to 20 MiB each with a 30-second socket timeout. Normalized archive payload is capped
at 95 MiB and must pass the existing reader's 50 MiB compressed/100 MiB expanded
limits. Requests are spaced at least 13 seconds after the preceding response.
Run only one downloader/client per account; separate processes share the provider's
quota, and the tool cannot coordinate with them. A rate-limit error stops the run.

## Bounded archive contract

Each run supports 1–10 unique uppercase alphanumeric stock symbols, one inclusive
window of at most 31 completed calendar days, and the reviewed 2026 calendar only.
Each symbol and `C:GBPUSD` gets one ascending, unadjusted, one-minute request with
limit 50,000. Even a 31-day window across a DST fallback is below that base-minute
limit. Unexpected pagination, empty series, non-OK status, adjusted data, bad OHLC,
duplicate/out-of-order timestamps and records outside the requested ET dates fail.

Stock rows retain only scheduled regular-session minutes. Fractional values remain
exact decimal JSON numbers. All requested exchange sessions stay in the manifest,
including days with no stock bars. Missing minutes are reported, never filled;
the default downloader may save a sparse nonempty series for inspection. Strict
validation and the baseline runner still reject incomplete coverage. A wholly
empty symbol/FX response fails rather than publishing an unusable archive.

The ZIP includes the existing raw-price JSONL files, `GBPUSD_completed_fx.jsonl`,
and `acquisition.json`. The manifest inventories all payload sizes and SHA-256
digests. Acquisition metadata records safe request URLs, retrieval time, source
response hashes and retained row counts. It does not store keys, arbitrary vendor
metadata, raw HTTP bodies or provider error text. Hashes establish integrity, not
an authenticated vendor signature or independent price correctness.

All requests and validation finish before publication. A private temporary ZIP is
validated and published by an exclusive hard link; existing paths and competing
writers are preserved. The temporary directory is removed on handled failure.
Use a local filesystem supporting hard links (for example NTFS, APFS or ext4);
unsupported filesystems fail without a nonexclusive overwrite fallback. A killed
process may leave a temporary directory requiring manual removal.

## FX interpretation

Massive's forex aggregates use quoted prices, not executed currency trades. We
retain the GBP/USD close (USD per GBP), invert it with 28-digit decimal precision,
and timestamp the resulting GBP-per-USD observation at the minute's completion.
The original minute start and `historical-completed-bar-proxy-v1` label are retained.
The full date range includes pre-open FX minutes; a 09:29 minute can inform the
09:30 stock opening, while the 09:30 FX minute cannot.

This is a modelled historical valuation proxy. Bar-end availability is not proof
of actual data delivery time; historical corrections, spread, executable conversion
prices and quote gaps remain research limitations. Normal stock validation does
not establish FX freshness or coverage. The archive alone is not a backtest scenario:
costs, initial currency conversion and explicit settlement instructions remain
required, and FX must be matched causally with the simulator's freshness checks.

## Brokerage costs are a separate input

The checked [IBKR US-stock schedule](https://www.interactivebrokers.co.uk/en/pricing/commissions-stocks.php)
lists the lowest-volume tier at $0.0035/share with a $0.35 order minimum, and fixed
pricing at $0.005/share with a $1 minimum, subject to caps and applicable charges.
Routing, account eligibility and third-party fees matter; directed API orders are
not eligible for tiered pricing. The
[spot-currency schedule](https://www.interactivebrokers.co.uk/en/pricing/commissions-spot-currencies.php)
lists 0.20 basis points with a $2 minimum at its first tier; automatic conversion
typically adjusts the rate by 0.03% without a separate commission.

These published examples are not a qualified historical cost model. Rates and
regulatory fees can change by date, and the eventual account/routing/FX arrangement
is unknown. Reconcile dated charges and stress spread/slippage before interpreting
returns. The synthetic examples' fixed fees and FX are invented assumptions.
