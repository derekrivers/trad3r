# Trad3r

An offline-first research project for a small, personal trading experiment.
Current scope: historical bar replay, offline cash/position accounting, durable
risk observations and a broker-free synthetic order writer and reconciler.
The first [registered historical engineering runs](docs/first-engineering-results.md)
are complete: eight candidates per cost case, all rejected by the £3 risk cap,
zero trades and zero contribution above the same-cash reference.
There is no broker connection, real order execution, AI trading decision or live
mode. A single-session simulator now includes a frozen experimental opening-range
hypothesis; it has no validated performance or profitability evidence.

## Delivery plan

The [canonical project plan](docs/project-plan.md) defines delivery order and owner
gates. Follow the [64-task delivery register](docs/task-register.md),
[current status and next tasks](docs/project-status.md) and
[decision record](docs/decisions.md). The discretionary product will propose
traceable theses and conditional plans; deterministic code retains account, risk
and execution authority. The existing baseline is a comparison hypothesis.

## Run locally

For recoverable offline jobs, see the [VPS operations guide](docs/vps-operations.md).
The [ATLAS synthetic milestone](docs/vps-deployment-2026-10-10.md) has a pinned,
network-disabled runtime with verified recovery and local restore. Historical
reproduction and off-host backup remain open; no daily job is scheduled.
Run `python -m trad3r rehearse-controls runs/controls-01` for a new synthetic control
drill; see [paper readiness and remaining gates](docs/paper-readiness.md).

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

The separate [local acquisition command](docs/acquisition.md) plans and explicitly
downloads raw stock minutes plus historical GBP/USD valuation proxies from an
existing Massive account. It defaults to a dry run, prompts securely for a local
key, paces read-only requests and refuses overwrites. No subscription is purchased.
[`prepare-baseline`](docs/preparation.md) then builds a scenario from the combined
archive and explicit fixed-cost/conversion assumptions, checks causal FX freshness
and requires the exact same archive when running the baseline.
Connected Massive exports can also be combined with an existing stock archive using
[`attach-fx`](docs/acquisition.md#connected-massive-exports). The recorded sample now
has complete modelled FX coverage for every simulated valuation boundary; historical
strategy performance and account-specific execution economics remain unqualified.
The [experiment workflow](docs/experiments.md) freezes exact inputs and code before
running, saves both accounts and their journals in an immutable result bundle, and
rechecks accounting/metric integrity with `inspect-experiment`.

The [accounting contract](docs/accounting.md) describes supplied fill events, GBP/USD
cash, fees, external flows and explicit settlement. Its synthetic example is an
accounting check, not strategy performance.

The [entry diagnostic](docs/entry-checks.md) checks coherent risk/ledger snapshots,
all-in planned loss, exposure, settled cash, entry windows and attempt counts.
It neither reserves cash nor authorises live orders.

The [durable order lifecycle contract](docs/order-lifecycle.md) defines stable
identities, allowed transitions, uncertain submissions and synthetic fault cases
for Phase 4. [Atomic synthetic admission](docs/order-admission.md) persists intents,
attempts and cash/risk reservations together. The
[synthetic single writer](docs/order-writer.md) adds fenced ownership and a durable
marker-before-call boundary with deterministic acknowledgement, rejection and
lost-acknowledgement fixtures. [Synthetic reconciliation](docs/order-reconciliation.md)
adds cumulative order, execution, USD cash, position, commission and empty-settlement
evidence with atomic accounting and restart/disconnect fencing. Empty-order
snapshots still check cash and settlement and persist risk halts; older-order
evidence preserves newer reservations or records an unresolved exposure conflict.
These components have no broker or network endpoint.

The [P4.5 protection contract](docs/order-protection.md) defines cancellation races,
shared sell reservations, reducing exits and incident recovery, with 24 acceptance
scenarios and an ordered implementation handoff. This design is specified; its
pure [package A evaluator](docs/order-protection.md#package-a-implementation) now
derives exposure, protection and request-specific permissions without persistence
or dispatch. It retains terminal fee reservations, checks current quantity proofs
and applies the reviewed exchange-session bounds. Package B adds an explicitly
selected fresh v4 store with atomic shared sell-quantity and fee reservations,
replay against retained entry evidence and no dispatch path. New allocations
require fresh snapshot/quote/FX evidence and a current fenced writer within the
account's existing regular session. Allocation identity incidents block new
entries and submission markers. [Package C](https://github.com/derekrivers/trad3r/pull/38) adds cumulative v4 buy/sell evidence,
execution-level fee finality and pending T+1 lots without making proceeds spendable.
[Package D](docs/order-cancellation.md) adds a durable marker-before-call
cancellation journal, fenced synthetic outcomes and resolution from cumulative
entry or reducing evidence. Acceptance alone releases no quantity, cash or risk.
Reducing dispatch and packages E–G remain pending.

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
