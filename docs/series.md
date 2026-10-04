# Multi-session accounting scenarios

`python -m trad3r simulate-series runs/series.json` accepts a JSON object with a
`sessions` array. Each element uses the [single-session scenario](simulation.md)
contract. Only the first includes `funding`. Dates must be strictly increasing and
unique, with one symbol per session. Inline bars or a single `--archive` are
supported; with an archive, omit `bars` from every scenario. FX observations and
signals remain explicit per-session inputs. Keep licensed scenarios outside git.

The series funds **one** GBP 1000 research account and performs its initial FX
conversion once. All cash, pending sale proceeds, realised P&L and loss latches
carry forward. At the start of later supplied sessions an explicit `settle` event
releases only proceeds eligible under the [research release policy](settlement.md).
The account is valued with that session's fresh FX, including unsettled USD cash.
No missing days or intraday FX observations are invented. An unobserved loss
between supplied observations cannot be detected by this replay.

## Period review is still required

The initial session/week baselines are never renewed. A later date adds
`period_review_required` and blocks new entries while settlement, valuation and
loss observation continue. The reported daily/weekly P&L stays measured from the
displayed initial baseline dates. It must not be read as a fresh daily budget.
All halts remain latched, including an overall loss observed while flat, even
after FX/equity recovers. This is accounting continuity, not a completed
multi-day strategy backtester. An owner-reviewed transition workflow remains a
separate requirement; do not concatenate freshly funded single-session results.

Session attempt counters are local to each session, but their reset does not
remove the period block. Each session flattens at noon or the end of its supplied
slice; open positions cannot cross the boundary. A different symbol can be used
in a later flat session. Simultaneous multi-symbol execution is not implemented.

## Results and failure handling

The result contains per-session diagnostics, one final account report, preserved
baseline identifiers, current block reasons and **one** complete ledger event
journal. Event IDs are unique across the run; timestamps remain chronological.
Replaying that journal reconstructs the final ledger, including settlement.
Per-session P&L fields are cumulative account snapshots, not returns to sum.

The CLI emits a report only when every session succeeds. Invalid later input
produces no partial success JSON. Runs are isolated in memory and never read,
reset or modify the durable risk database. Restart recovery, atomic order/risk
storage and broker reconciliation remain open. All output disables live trading.
