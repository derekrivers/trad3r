# Scheduled settlement and research cash availability

Calendar ID: `us-equity-t1-2026-reviewed-2026-10-04`.
Cash-release policy: `explicit-event-after-settlement-day-new-york-v1`.

This module models scheduled regular-way US cash-equity settlement for 2026.
The scheduled date and the research cash-release cutoff are different concepts.
Neither is a confirmation that a real broker has received cash.

## Sources and scope

Checked 4 October 2026:

- [SEC investor bulletin on T+1](https://www.investor.gov/introduction-investing/general-resources/news-alerts/alerts-bulletins/investor-bulletins/new-t1-settlement-cycle-what-investors-need-know-investor-bulletin): standard applicable US stock transactions settle one business day after trade date.
- [DTC notice 23036-25, anticipated 2026 schedule](https://www.dtcc.com/-/media/Files/pdf/2025/10/15/23036-25.pdf): full closures and the distinction between limited services and no settlement services.
- [NSCC notice a9732, Good Friday 2026](https://www.dtcc.com/-/media/Files/pdf/2026/3/6/a9732.pdf): NSCC closure and no CNS processing on 3 April.
- [NSCC notice 9778, Independence Day 2026](https://www.dtcc.com/-/media/Files/pdf/2026/6/5/a9778.pdf): holiday closure on 3 July.

The DTCC notices were available in search-indexed publisher text; direct retrieval
of the older PDF routes was unavailable during review. Refresh these references
against current publisher notices when extending the calendar. No PDF is bundled.

The reviewed model excludes weekends and these twelve dates from regular-way
settlement: 1 and 19 January, 16 February, 3 April, 25 May, 19 June, 3 July,
7 September, 12 October, 11 and 26 November, and 25 December. In particular,
12 October and 11 November are exchange trading days but not settlement days.
Limited DTC operations on 3 April and 3 July do not make them ordinary equity
settlement days. The early-close dates 27 November and 24 December remain
settlement days. UK bank holidays are not substituted for this US schedule.

These are scheduled dates, not an operational-status feed. Instrument exceptions,
special settlement terms, settlement failures and emergency closures are outside
this model. Extending years or changing dates requires a reviewed PR with sources,
tests and a new calendar ID. Trades whose next settlement date falls outside 2026
fail closed: a 31 December trade is currently unsupported.

## Date calculation and validation

`settlement_date(trade_session)` requires a supported exchange session and returns
the next supported settlement business day. The ledger derives a sale's trade date
in New York from its UTC timestamp. It does not model overnight-session business
date assignments or validate the execution hours of caller-supplied ledger fills.

The simulator calculates `settles_on` when omitted. If supplied, it must match the
calculation exactly. Ledger sale events retain an explicit `settles_on` assertion;
wrong dates, including later dates, are rejected transactionally. Model a delayed
cash release by delaying the `settle` event, not changing the scheduled date.

## Conservative cash-release assumption

Our research policy withholds sale proceeds for the **whole scheduled settlement
day in New York**. An explicit `settle` event can release them at or after the next
New York midnight. This is a deliberately late modelling cutoff, not a statement
of a broker's actual intraday settlement or buying-power policy. It can reduce
capital reuse compared with a broker that makes settled cash available earlier.
It also cannot guarantee availability when real settlement fails or is delayed.

For a Friday 4 September sale, Labor Day is skipped: scheduled settlement is
Tuesday 8 September; the earliest research release is Wednesday 9 September at
04:00 UTC (00:00 New York). A Tuesday 10 November sale skips Veterans Day, settles
Thursday 12 November, and is releasable Friday 13 November at 05:00 UTC.
The different UTC hours follow New York daylight saving rules.

Reaching the cutoff alone does not mutate cash. A `value` event still includes
pending proceeds in equity, but cannot make them spendable. `settle` releases only
eligible lots, does not change equity, and cannot credit a lot twice. Pending cash
cannot fund purchases, withdrawals or FX. Reports expose each pending amount,
scheduled date and `available_at`, plus both policy identifiers.

The single-session simulator never releases sale proceeds within its session.
Purchases still require and immediately debit settled cash. Future multi-session
research must preserve one account and loss history across sessions. A real broker
integration will additionally need confirmed settlement and reconciled cash; this
offline event stream is not authority to trade or withdraw money.
