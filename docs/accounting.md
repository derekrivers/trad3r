# Offline accounting contract

`python -m trad3r ledger examples/ledger.json` replays supplied events and prints
one final valuation. The example uses invented prices, not a trading strategy.
Fill events are assertions supplied by the caller; this module neither generates
fills nor claims they could have executed. It has no broker or network capability.

Each event has a unique string `id`, UTC `at`, and `type`. Events are chronological;
equal timestamps preserve input order. Duplicates and backwards timestamps fail.
Amounts use decimal strings. Invalid events roll back all in-memory changes.

| Type | Additional fields | Effect |
| --- | --- | --- |
| fund | amount | Initial GBP 1000 exactly once, before other events |
| deposit / withdraw | currency, amount, usd_to_gbp | GBP/USD external flow; withdrawals require settled cash |
| exchange | from_currency, amount, received, fee_gbp | Explicit executed conversion amounts, with GBP fee |
| buy | symbol, quantity, price, fee_usd, usd_to_gbp | Whole USD shares, funded from settled USD cash |
| sell | symbol, quantity, price, fee_usd, usd_to_gbp, settles_on | Realises cost basis; net proceeds become unsettled USD |
| settle | none | Releases eligible lots after their full settlement day in New York |
| value | usd_to_gbp, prices | Current GBP equity; prices must contain exactly the held symbol |

All FX inputs are GBP per USD. `value` must be the final event. Its timestamp is
an assertion that the supplied marks are current at that time; automatic price
freshness and independently sourced FX are not implemented. Every state-changing
event invalidates the previous valuation. Only one symbol may be held, but adding
to that position is supported. Borrowing, short sales and fractional shares fail.

Entry fees enter GBP position basis using entry FX. Average-cost partial sales
allocate basis to eight GBP decimal places, with the final sale consuming the exact
remaining basis. Exit fees reduce proceeds and realised trade P&L. Position value
and cash, including unsettled proceeds, are revalued at valuation FX. Total account
P&L subtracts initial funding and later external flows. Realised trade P&L plus
unrealised position P&L does not necessarily equal account P&L: currency cash gains,
conversion costs and fees can account for the difference. Account P&L is the risk
input, never the sum of the two trade-only figures.

Sale settlement dates must match the [bounded 2026 T+1 calendar](settlement.md).
The trade date is derived in New York. Research proceeds remain unavailable for
the entire scheduled settlement day, then require an explicit `settle` event.
Reports identify the calendar and release policy and list pending amounts/dates
and earliest research release timestamps. This replaces the old UTC-date release
rule: old event files with incorrect dates now fail instead of replaying silently.
Purchases debit settled cash immediately. Broker cash availability, failed or
delayed settlement and real reconciliation remain future work.

This ledger does not enforce trade-risk, exposure or entry-frequency limits, decide
whether to enter a trade, or guarantee persistence. Those belong to the execution
and durable risk layers. The source event file can reconstruct the ledger exactly.
Corporate actions, dividends, taxes, multiple positions and live accounts are out
of scope. External project costs are not silently deducted from account equity.
