# Bounded exchange calendar

Calendar ID: `us-equities-2026-reviewed-2026-10-04`.
Coverage is **2026 only**, for scheduled NYSE/Nasdaq cash-equity regular sessions.
Dates outside this year raise an error, including in entry diagnostics. There is
no weekday fallback, runtime download, or dependency on the machine's current date.

Sources checked 4 October 2026:

- [NYSE holidays and trading hours](https://www.nyse.com/trade/hours-calendars)
- [Nasdaq Trader 2026 holiday schedule](https://www.nasdaqtrader.com/Trader.aspx?id=Calendar)

Both list ten full weekday closures: 1 and 19 January, 16 February, 3 April,
25 May, 19 June, 3 July, 7 September, 26 November and 25 December. Weekends are
closed. Both list 13:00 Eastern closes on 27 November and 24 December. The ordinary
regular session is 09:30–16:00 Eastern. In particular, 2 July is a full session;
bond-market early closes must not be substituted for equity hours.

`session_bounds` returns UTC opening/closing timestamps using IANA New York rules,
or no session for a scheduled closed date. A minute bar's start must be within
the half-open interval [open, close). Thus an ordinary final bar begins at 15:59,
and an early-close final bar at 12:59. Whole bars starting at the closing auction
time are excluded. UK clock changes do not define US session boundaries.

Archive parsing validates every bar and every declared expected session. It still
reports counts rather than asserting complete minute coverage. Entry diagnostics
reject scheduled closed days; the existing 10:00–11:30 entry window and noon
flatten remain unchanged on early-close days. The simulator rechecks all supplied
bar times, including when callers construct Bar objects directly. Validation,
replay summaries, entry diagnostics and simulation reports record the calendar ID.
Replay journal bar payloads remain unchanged.

This is a versioned schedule snapshot, not a live exchange-status service. It does
not model unscheduled closures, instrument halts or special sessions. Extending
coverage or changing dates requires checking official exchange publications,
updating the version, tests and documentation, and reviewing a PR. This year bound
deliberately constrains broader backtests until their dates have been checked.

## Separate settlement work

Do not use the next exchange session as an automatic settlement date. This module
does not establish clearing or cash availability, and must not release unsettled
cash. The ledger and simulator still accept an explicitly supplied future
`settles_on`; it is not verified against an official settlement schedule. A separate
clearing-calendar contract and broker cash-availability reconciliation remain
prerequisites for multi-session execution.
