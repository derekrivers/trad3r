# Account-level engineering evaluation

`baseline-backtest` includes an `account-evaluation-v1` report and a complete
`no-trade-same-cash-v1` reference run. Both remain engineering scenarios. Metrics
describe declared inputs and simulated fills; they are not a validation verdict,
probability of profit, annualised return or estimate of passive income.

## Accounting first

Each report reconstructs the run's ledger and checks that it ends flat and matches
the emitted final valuation. It never sums cumulative daily snapshots. The equity
curve preserves every observed valuation and its ledger event ID, including
multiple observations at the same timestamp after fills or period checks.

| Field | Meaning |
| --- | --- |
| `net_account_pnl_gbp` | Final equity minus £1,000 and net later external contributions |
| `net_account_return` | That account P&L divided by £1,000; not annualised |
| `realised_trade_pnl_gbp` | Net GBP trade proceeds minus allocated GBP acquisition basis, including fill commissions |
| `max_observed_drawdown_gbp` | Largest decline in cash-flow-adjusted equity from its running observed peak, initially £1,000 |
| `max_observed_loss_from_initial_gbp` | Largest observed loss relative to the original £1,000 basis, floored at zero |
| `explicit_commissions_gbp` | Entry/exit USD commissions translated at their event FX rates |
| `explicit_conversion_fees_gbp` | Explicit GBP fees on currency-exchange events |
| `gross_turnover_gbp` | Sum of buy and sell notionals translated at each event's FX rate |
| `simulated_position_seconds` | Total simulated time from entry until the position is fully closed |
| `trade_win_fraction` | Fraction of closed trades with strictly positive realised GBP trade P&L; null with no closed trades |

Commission and conversion fees are already included in equity/P&L: do not deduct
them a second time. Modelled slippage is embedded in execution prices, not a
separate fee debit. Realised trade P&L excludes idle cash's FX movement and currency
conversion fees; account P&L includes them. An account gain is not automatically
a winning trade. The report does not infer intraminute or overnight equity paths.
Observed drawdown can understate losses between recorded observations.

## All candidates and sessions remain visible

Reports count generated candidates, entries, closed trades, rejected/expired
candidates, no-candidate sessions and sessions blocked at their final observation.
Rejected candidates are not no-candidate days. Rejection reason counts are not
mutually exclusive: one candidate can fail several checks. Exit reason counts,
individual net trade results and the full trace remain available for inspection.
No-candidate and post-halt sessions stay in the account record and denominators.

## Same-cash reference

The reference is a separate counterfactual account funded once with the same
£1,000 and initial GBP-to-USD conversion, including its explicit fee. It consumes
the same dates, bars and timestamped FX but generates no trades. The approved
rollover/observation policy still applies; no trading commissions are charged when
there are no fills. It is not an all-GBP cash benchmark, deposit product or funded
second real account, and earns no assumed interest.

`comparison.net_account_pnl_difference_gbp` is baseline final account P&L minus
reference final account P&L. It shows the incremental result of simulated trading
under those inputs, including changes to the amount of USD cash held. It is not
statistical alpha or evidence of a repeatable edge. Both complete ledger journals,
input hashes, final reports and evaluation curves are included for reconciliation.

## Remaining qualification

The synthetic walkthrough deliberately uses invented prices and assumed costs/FX.
Before credible historical interpretation, supply qualified FX/history/cost
evidence and register untouched chronological partitions, cost/latency stress
assumptions, sample-sufficiency requirements and acceptance criteria. The current
inspected 20-session sample remains an engineering fixture. No classifier is
trained, and there is no automatic pass-to-paper or pass-to-live threshold.
