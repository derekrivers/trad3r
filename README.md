# Trad3r

An offline-first research project for a small, personal trading experiment.
Current scope: deterministic historical bar replay and pure risk-policy checks.
There is no broker connection, order execution, strategy, simulated fill engine,
cash ledger, AI trading decision or live mode in this version.

## Run locally

Python 3.11+; no runtime dependencies. From the repository root:

```sh
python -m unittest discover -s tests -v
python -m trad3r --help
python -m trad3r risk-check docs/risk-example.json
```

Use `py` on Windows or `python3` on systems where that is the Python command.
Optional installation: `python -m pip install -e .` provides the `trad3r` command.

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

## Risk policy

The agreed initial capital is £1,000, with a £300 cumulative account-loss halt.
Account P&L is equity minus initial capital minus later deposits plus withdrawals.
The initial floor is £700 absent external flows. It is not a trailing stop.
Planned risk per trade includes costs and is capped at £3; daily and weekly loss
triggers are £10 and £25, measured from cash-flow-adjusted period baselines.

`risk-check` evaluates supplied GBP snapshots. Equity must already include
unrealised P&L, fees and currency effects. Previously latched reasons are preserved
when supplied. Durable halt storage and a reviewed reset procedure are not yet
implemented. These calculations are not a live safety system or a guarantee of
maximum loss. See [risk policy](docs/risk-policy.md).

## Data and implementation status

The first private sample contains AAPL, MSFT and F over 20 sessions, with 23,400
distinct regular-session minute observations. These are engineering fixtures,
not investment recommendations or evidence of a profitable strategy.

Market data and API keys must stay outside this public repository. Tests generate
synthetic bars locally; CI needs neither licensed data nor credentials. See
[data contract](docs/data.md) and [delivery roadmap](docs/roadmap.md).
