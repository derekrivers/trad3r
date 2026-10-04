# Research readiness and next inputs

Current result: **engineering inputs and approved isolated rollover available;
qualified strategy evaluation remains blocked**. Passing tests and complete bars do not qualify trading
results. Synthetic demonstrations now produce descriptive metrics; no qualified
historical strategy return, win rate or passive-income estimate has been produced.

## Reproduce the inventory

```sh
python -m trad3r research-audit data/trad3r_sample.zip --start 2026-09-04 --end 2026-10-02
```

The dates are explicit and inclusive. The command compares every scheduled minute
for every declared symbol against the entire requested window, including dates
absent from the manifest. Weekends/holidays are excluded and early closes use their
shorter grid. Dates outside the reviewed 2026 calendar fail closed. It reads and
hashes the archive without changing it, running a strategy or inspecting P&L.

Output separates `declared_coverage_complete` from `structurally_complete` for the
requested window. `research_ready` is always false in this version: the command
cannot verify external evidence or certify research readiness. The blocker list
is a repository capability checklist, not a scan of files elsewhere on the user's
computer. Exit 0 means the diagnostic ran successfully, including when blocked;
invalid input exits 2 without success JSON. Consumers must read the result fields.

## Recorded engineering evidence

Audit on 2026-10-04 of source SHA-256
`eebd9e7454227356d9b7d1bcbe9e1518bcd18721fdf441a9179e19a3b534074b`:

| Item | Finding |
| --- | --- |
| Requested window | 2026-09-04 through 2026-10-02 |
| Scheduled sessions | 20 |
| Declared symbols | AAPL, MSFT, F |
| Distinct regular-session raw minute bars | 23,400 |
| Missing minutes or omitted sessions in that window | 0 |
| Data role | Already-inspected engineering fixture |
| Qualified untouched evaluation data | Not supplied |
| Qualified timestamped FX / broker cost evidence | Completed historical FX proxy now available; independent FX qualification and dated broker cost evidence remain open |

Do not relabel this inspected sample as an untouched final test set. Archive
checksums establish file identity, not economic accuracy, legal entitlement,
point-in-time universe selection or authentic vendor delivery timestamps.

On 2026-10-04 the connected Massive plugin supplied 29,894 unique GBP/USD minute
records for the same date window. The private combined archive has SHA-256
`6ba4e7fca0e6b875997d6a7ac81ede3f2356dedbb72f1ead73edce80dbc24f8a`.
Its original 23,400 stock payload observations are preserved. All 3,020 opening-to-noon
valuation boundaries across the 20 sessions have a completed FX observation with
zero modelled age at that boundary. Three AAPL minutes also matched the original
sample's OHLC and fractional volume through the connected endpoint; that is a
same-provider consistency check, not independent price verification.

Connector CSV SHA-256:
`6559a3fefc27181ed4b42ab965396cda13c58049b861dfdbdd502a0647fc87a7`.
Preparation succeeded with explicitly invented engineering cost/conversion inputs;
the strategy was not run and no historical P&L was inspected. The FX remains a
corrected historical quote-derived proxy, not a broker execution rate or authentic
delivery-time record. The data-access blocker for this fixture is resolved.

## Inputs needed for the next meaningful result

| Dependency | Concrete input / decision | What it unblocks |
| --- | --- | --- |
| Period transitions | Resolved for isolated backtests: owner approved option B on 2026-10-04; [research scenario implementation](research-series.md) available | Frozen strategy integration now carries one continuous £1,000 account |
| Broader stock history | Licensed raw minute exports, symbols/date inventory, provider metadata, acquisition date and rights/retention notes | Independent checks and chronological development/validation/test planning |
| USD/GBP history | UTC observation timestamps, rate direction, source, provenance and delivery/availability convention | GBP equity, cash and risk accounting across the same period |
| Execution economics | Dated intended account/instrument fee schedule; minimum commissions, FX conversion costs and market-data charges; bid/ask evidence or documented spread/slippage stress assumptions | Assessing whether a one-share hypothesis can survive actual costs |
| Data quality | Corporate-action evidence and independent price checks; explicit missing-data/closure policy | Avoiding artificial jumps, hidden missing dates and unexplained anomalies |

Never paste passwords or API secrets into repository files, PRs or chat. A broker
account is not needed to supply historical exports or documented fee assumptions.
No paid acquisition is authorised by this document; the £10/month operating budget
remains a feasibility constraint. Current account-specific data entitlements and
costs must be checked before choosing a source or purchasing anything.

## Evaluation protocol to register before looking at outcomes

1. Record the strategy/schema identifiers, exact source hashes, code commit,
   symbol selection rationale, inspected-data exclusions, cost model and the
   approved period policy in a versioned experiment manifest.
2. Inventory the newly available sessions, then reserve explicit chronological
   development, validation and final test periods before inspecting their strategy
   outcomes. Do not random-split minute rows or recycle this engineering sample as
   final validation. Select sample-size requirements and acceptance criteria before
   evaluating results; 20 inspected sessions do not establish those requirements.
3. Preserve a single account through each continuous evaluation run: starting
   capital once, costs, FX, pending settlement, all observations and all halts. Never
   concatenate independently funded daily runs. A halt ends entry eligibility;
   recovery does not erase it. Report rejected and expired candidates as well as
   filled trades, time blocked and cash availability.
4. Report net account equity/P&L, worst equity loss, drawdown, costs, turnover,
   trade count and exposure alongside the no-trade account under the same cash/FX
   assumptions. Include flat/no-candidate sessions. Evaluate predeclared adverse
   spread, fee, latency and gap scenarios; disclose uncertainty and data limits.
5. Keep an append-only experiment register, including failed variants. Freeze the
   selected rules before opening the final test. Once inspected, that test cannot
   be reused to claim untouched validation of a revised strategy. No statistical
   significance or profitability claim comes from selecting the best variant.

This is the protocol structure, not a completed pre-registration: actual dates,
data sufficiency and numeric acceptance criteria require the missing inventory and
economic inputs. Those values must not be invented to make a report pass.

## Later classifier work

Only after a useful baseline evaluation should we create net-cost outcome labels
with explicit observation and label-end times. Features must exist at decision
time. Fit imputation/scaling/selection only on the training partition, purge labels
whose outcome horizon overlaps the next partition and keep same-session events
together. Tune model/threshold choices on validation only; assess calibration and
incremental results versus the same frozen unfiltered baseline on untouched data.

Begin any Jev or other classifier in shadow mode. Its score can be logged or later
used as an entry filter, but cannot increase size, relax a risk limit or clear a
halt. A classifier's confidence is not a verified probability of profitable fills.
Training is currently blocked on qualified labelled data and this evaluation
protocol; adding an AI call now would not supply the missing evidence.

## Ordered engineering continuation

The [local downloader and connected FX import](acquisition.md) and
[offline scenario preparation](preparation.md) are available. Stock and FX access
through the installed Massive plugin is verified for the recorded fixture.
No API key belongs in chat or GitHub. Preparation validates causal timing and source
identity but deliberately retains an engineering-only status and explicit assumed
costs. Published price schedules do not establish account-specific historical fees.

The [continuous baseline runner](baseline-backtest.md) now preserves the approved
rollover policy, audit records and halts, and includes account-level summaries and
a same-cash no-trade comparison. Next obtain the qualified inputs, register actual
experiment dates/acceptance criteria and implement chronological evaluation against
that inventory. Broker order persistence/recovery and forward paper execution
remain later work after account/data economics and execution contracts are known.
