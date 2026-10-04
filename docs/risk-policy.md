# Agreed risk policy

Planning baseline recorded 4 October 2026. Changes require an explicit owner decision.

| Rule | Value |
| --- | --- |
| Eventual initial live capital | £1,000, after validation and paper trading |
| Cumulative account loss trigger | £300, inclusive |
| Planned loss per trade | £3 including round-trip costs and slippage allowance |
| Session loss trigger | £10, inclusive |
| Trading-week loss trigger | £25, inclusive |
| Recurring external operating budget | £10/month; one-off purchases reviewed separately |

Account P&L = GBP net liquidation equity − 1,000 − subsequent deposits + withdrawals.
The £300 loss trigger is absolute from the funding baseline, not from peak equity.
A later deposit cannot erase a loss; a withdrawal alone is not a trading loss.
Fees, dividends and sale proceeds are not owner deposits or withdrawals.

Daily and weekly P&L compare cash-flow-adjusted equity against the respective
start mark. Future session and week boundaries must use a specified exchange
calendar. A process restart cannot choose a fresh baseline. Overall stops remain
latched until explicit owner review; daily/weekly resets require both a new period
and review. No timer-based loss-budget renewal is authorised.

Project P&L additionally deducts externally paid data/hosting/AI bills. Do not
double-count costs already debited from account equity. The eventual operational
design has no borrowing, derivatives or shorting; at most one position, three
entry attempts per session and £500 simulated exposure are proposed defaults.
These exposure and frequency controls are not implemented in this first increment.

## Implementation boundary

`risk.py` implements Decimal-based P&L arithmetic, inclusive threshold assessment,
preservation of caller-supplied halt reasons and planned long-trade loss estimation.
The separate `risk_store.py` persists observations and latches transactionally.
Neither module validates mark freshness, reconciles a broker, liquidates
positions, chooses quantities, or resets session baselines. The offline ledger
checks settled cash for supplied fills; order admission remains future work.
The CLI does not trade. An assessment is a diagnostic, not an order authorisation.

Stops may be overrun by gaps or unavailable execution. AI must never change a
limit, reset a halt, receive broker credentials or approve live activation.

See [durable risk state](risk-state.md) for restart behaviour, concurrency checks,
period-review blocking and the distinction between a diagnostic and order authority.
