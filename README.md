# Trad3r

An offline-first research project for a small, personal trading experiment.
Current scope: historical bar replay, offline cash/position accounting and durable risk observations.
There is no broker connection, real order execution, AI trading decision or live
mode. A single-session simulator now includes a frozen experimental opening-range
hypothesis; it has no validated performance or profitability evidence.

## Run locally

Python 3.11+ with IANA timezone data. From the repository root:

```sh
python -m unittest discover -s tests -v
python -m trad3r --help
python -m trad3r risk-check docs/risk-example.json
python -m trad3r ledger examples/ledger.json
python -m trad3r simulate examples/simulation.json
```

Use `py` on Windows or `python3` on systems where that is the Python command.
Installation: `python -m pip install -e .` provides the `trad3r` command and
installs timezone data on Windows. On minimal Linux images without system timezone
data, also install `tzdata` using pip. Standard Linux/macOS installs use system data.

Place your own licensed sample ZIP outside git, for example in `data/`:

```sh
python -m trad3r validate data/trad3r_sample.zip
mkdir runs
python -m trad3r replay data/trad3r_sample.zip --journal runs/replay-01.jsonl
python -m trad3r replay data/trad3r_sample.zip --journal runs/replay-02.jsonl
```

Identical inputs produce identical journal bytes and SHA-256 values. Output files
are created exclusively, so existing results cannot be silently overwritten.
Replay emits completed bars, ordered by availability time and then symbol. A
13:30 bar becomes available at 13:31. No trades or profit figures are generated.
Only raw-price series are replayed; adjusted copies are not additional observations.
Use `--require-complete` to reject missing scheduled minutes and `--batches` on
replay to emit all declared symbols together at each completed-minute timestamp.
See the [coverage and batch contract](docs/data.md).

## Risk policy

The agreed initial capital is £1,000, with a £300 cumulative account-loss halt.
Account P&L is equity minus initial capital minus later deposits plus withdrawals.
The initial floor is £700 absent external flows. It is not a trailing stop.
Planned risk per trade includes costs and is capped at £3; daily and weekly loss
triggers are £10 and £25, measured from cash-flow-adjusted period baselines.

`risk-check` evaluates supplied GBP snapshots. Equity must already include
unrealised P&L, fees and currency effects. Previously latched reasons are preserved
when supplied. The separate `risk-init`, `risk-record`, `risk-status` and
`risk-history` commands persist observations and halts across restarts. No reset
command exists. See the [risk-state walkthrough](docs/risk-state.md). These checks
are not a live safety system or a guarantee of maximum loss. See
[risk policy](docs/risk-policy.md).
The risk store reconstructs every historical assessment and loss latch before
returning status/history or accepting another observation; inconsistent earlier
audit records fail closed even if the latest snapshot appears consistent.

## Data and implementation status

The first private sample contains AAPL, MSFT and F over 20 sessions, with 23,400
distinct regular-session minute observations. These are engineering fixtures,
not investment recommendations or evidence of a profitable strategy.

Market data and API keys must stay outside this public repository. Tests generate
synthetic bars locally; CI needs neither licensed data nor credentials. See
[data contract](docs/data.md) and [delivery roadmap](docs/roadmap.md).

The [accounting contract](docs/accounting.md) describes supplied fill events, GBP/USD
cash, fees, external flows and explicit settlement. Its synthetic example is an
accounting check, not strategy performance.

The [entry diagnostic](docs/entry-checks.md) checks coherent risk/ledger snapshots,
all-in planned loss, exposure, settled cash, entry windows and attempt counts.
It neither reserves cash nor authorises live orders.

The [scenario simulator](docs/simulation.md) applies delayed entries, explicit
costs, stop-first intrabar ambiguity and scheduled flattening. It emits replayable
ledger events, not evidence of strategy profitability.

The [versioned exchange calendar](docs/calendar.md) validates scheduled 2026
NYSE/Nasdaq equity sessions, holidays and early closes. Other years fail closed.
The separate [settlement model](docs/settlement.md) calculates scheduled 2026 T+1
dates and holds proceeds until after the full settlement day in New York. Cash
release requires an explicit ledger event. Broker cash availability, unscheduled
closures and delayed/failed settlement still require separate reconciliation.

`simulate-series` carries one research account across supplied sessions, including
cash, settlement and loss latches. [Period changes block new entries](docs/series.md)
pending review; it does not automatically renew daily or weekly loss budgets.

The [feature exporter](docs/features.md) computes versioned descriptive snapshots
from completed batches, with explicit warmup nulls and no future-bar access. It
does not generate trade signals or train a classifier.

The [frozen strategy hypothesis](docs/strategy.md) generates at most one one-share
opening-range candidate per selected symbol/session. `strategy-signals` exports
candidates from a complete archive; `baseline-simulate` passes generated candidates
through the existing execution and risk checks using explicit costs and FX.

`research-audit ARCHIVE --start YYYY-MM-DD --end YYYY-MM-DD` checks the full
requested session window, including dates omitted from the manifest, and reports
the [remaining research dependencies](docs/research-readiness.md). A structurally
complete archive does not establish strategy readiness. The next account-state
policy is the [approved offline period-transition exception](docs/period-transition-proposal.md).
`simulate-research-series` applies it to bounded isolated scenarios, carrying one
account across eligible periods and preserving every triggered halt. See the
[research rollover contract](docs/research-series.md); durable risk accounts and
ordinary series retain their period blocks.

[`baseline-backtest`](docs/baseline-backtest.md) connects the fixed hypothesis to
that continuous account over a complete session window and one preselected symbol.
A runnable synthetic example demonstrates the workflow without an account or data
credentials; qualified historical FX, costs and evaluation data are still needed.
Its [evaluation report](docs/evaluation.md) includes observed equity/drawdown, net
trade and account P&L, explicit fees, rejected candidates and a same-cash no-trade
reference. These are descriptive engineering metrics, not a readiness verdict.
