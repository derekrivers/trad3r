from copy import deepcopy
from datetime import date
from decimal import Decimal as D
import contextlib
import io
import json
from pathlib import Path
import tempfile
import unittest

from trad3r.__main__ import main
from trad3r.calendar import session_bounds
from trad3r.ledger import Ledger
from trad3r.settlement import (CASH_RELEASE_POLICY, SETTLEMENT_CALENDAR_ID,
                               cash_available_at, is_settlement_day, settlement_date)
from test_simulation import run, scenario


class SettlementTests(unittest.TestCase):
    def book(self, at="2026-09-04T14:00:00Z", quantity=1):
        book = Ledger()
        for event in (dict(id="fund", type="fund", amount="1000"),
                      dict(id="fx", type="exchange", from_currency="GBP", amount="80",
                           received="100", fee_gbp="0"),
                      dict(id="buy", type="buy", symbol="AAA", quantity=quantity,
                           price=str(100 // quantity), fee_usd="0", usd_to_gbp="0.8")):
            book.apply(dict(event, at=at))
        return book

    def sell(self, book, at="2026-09-04T14:01:00Z", due="2026-09-08", identity="sell"):
        book.apply(dict(id=identity, type="sell", at=at, symbol="AAA", quantity=1,
                        price="100", fee_usd="1", usd_to_gbp="0.8", settles_on=due))

    def value(self, book, at):
        book.apply(dict(id="value-"+at, type="value", at=at, usd_to_gbp="0.8", prices={}))
        return book.last_report

    def test_t1_weekdays_weekends_and_all_scheduled_holiday_spans(self):
        pairs = (("2026-01-02", "2026-01-05"), ("2026-01-16", "2026-01-20"),
                 ("2026-02-13", "2026-02-17"), ("2026-04-02", "2026-04-06"),
                 ("2026-05-22", "2026-05-26"), ("2026-06-18", "2026-06-22"),
                 ("2026-07-02", "2026-07-06"), ("2026-09-04", "2026-09-08"),
                 ("2026-09-08", "2026-09-09"), ("2026-10-09", "2026-10-13"),
                 ("2026-10-12", "2026-10-13"), ("2026-11-10", "2026-11-12"),
                 ("2026-11-11", "2026-11-12"), ("2026-11-25", "2026-11-27"),
                 ("2026-11-27", "2026-11-30"), ("2026-12-23", "2026-12-24"),
                 ("2026-12-24", "2026-12-28"), ("2026-12-30", "2026-12-31"))
        for trade, due in pairs:
            with self.subTest(trade=trade):
                self.assertEqual(settlement_date(trade).isoformat(), due)

    def test_exchange_and_settlement_calendars_are_distinct(self):
        for day in ("2026-10-12", "2026-11-11"):
            self.assertIsNotNone(session_bounds(day))
            self.assertFalse(is_settlement_day(date.fromisoformat(day)))
        self.assertFalse(is_settlement_day(date(2026, 1, 1)))
        for day in ("2026-11-27", "2026-12-24"):
            self.assertTrue(is_settlement_day(date.fromisoformat(day)))

    def test_closed_trade_dates_and_unknown_years_fail_closed(self):
        for day in ("2026-01-01", "2026-09-07", "2026-09-05", "2025-12-31",
                    "2027-01-04", "2026-12-31", "20260904"):
            with self.subTest(day=day), self.assertRaises(ValueError):
                settlement_date(day)

    def test_release_cutoff_is_midnight_after_due_day_in_new_york(self):
        for due, expected in ((date(2026, 9, 8), "2026-09-09T04:00:00+00:00"),
                              (date(2026, 11, 12), "2026-11-13T05:00:00+00:00"),
                              (date(2026, 12, 31), "2027-01-01T05:00:00+00:00")):
            self.assertEqual(cash_available_at(due).isoformat(), expected)
        for due in (date(2026, 9, 7), date(2026, 9, 5), date(2027, 1, 4), "2026-09-08"):
            with self.assertRaises(ValueError):
                cash_available_at(due)

    def test_wrong_sale_dates_reject_transactionally(self):
        book = self.book()
        book.apply(dict(id="mark", type="value", at="2026-09-04T14:00:00Z",
                        usd_to_gbp="0.8", prices={"AAA": "100"}))
        before = deepcopy(book)
        for due in ("2026-09-04", "2026-09-05", "2026-09-07", "2026-09-09", "20260908", None):
            with self.subTest(due=due), self.assertRaisesRegex(ValueError, "scheduled T\\+1"):
                self.sell(book, due=due)
            self.assertEqual(book, before)
        self.sell(book)
        self.assertEqual(book.unsettled, [(date(2026, 9, 8), D("99"))])

    def test_sale_trade_date_uses_new_york_not_utc_date(self):
        book = self.book(at="2026-09-08T14:00:00Z")
        self.sell(book, at="2026-09-09T00:00:00Z", due="2026-09-09")
        self.assertEqual(book.unsettled[0][0], date(2026, 9, 9))

    def test_year_end_unknown_settlement_leaves_position_unchanged(self):
        book = self.book(at="2026-12-31T15:00:00Z")
        before = deepcopy(book)
        with self.assertRaisesRegex(ValueError, "2026 dates only"):
            self.sell(book, at="2026-12-31T15:01:00Z", due="2027-01-04")
        self.assertEqual(book, before)

    def test_no_release_on_holiday_due_morning_or_utc_midnight(self):
        book = self.book()
        self.sell(book)
        for at in ("2026-09-07T14:00:00Z", "2026-09-08T14:00:00Z",
                   "2026-09-09T00:00:00Z", "2026-09-09T03:59:59Z"):
            book.apply(dict(id="settle-"+at, type="settle", at=at))
            self.assertEqual(book.cash["USD"], 0)
            self.assertEqual(len(book.unsettled), 1)
            for kind, fields in (("buy", dict(symbol="AAA", quantity=1, price="99", fee_usd="0", usd_to_gbp="0.8")),
                                 ("withdraw", dict(currency="USD", amount="99", usd_to_gbp="0.8")),
                                 ("exchange", dict(from_currency="USD", amount="99", received="79.2", fee_gbp="0"))):
                before = deepcopy(book)
                with self.assertRaisesRegex(ValueError, "settled cash"):
                    book.apply(dict(id=kind+at, type=kind, at=at, **fields))
                self.assertEqual(book, before)

    def test_explicit_release_preserves_equity_and_does_not_double_credit(self):
        book = self.book()
        self.sell(book)
        # A valuation after the cutoff cannot itself release any cash.
        at = "2026-09-09T04:00:00Z"
        before = self.value(book, at)
        self.assertEqual(before["unsettled_usd"], D("99"))
        self.assertEqual(before["pending_settlements"][0]["available_at"], "2026-09-09T04:00:00+00:00")
        self.assertEqual(before["settlement_calendar_id"], SETTLEMENT_CALENDAR_ID)
        self.assertEqual(before["cash_release_policy"], CASH_RELEASE_POLICY)
        book.apply(dict(id="settle", type="settle", at=at))
        after = self.value(book, "2026-09-09T04:00:01Z")
        self.assertEqual(before["equity_gbp"], after["equity_gbp"])
        self.assertEqual(after["settled_cash"]["USD"], D("99"))
        self.assertEqual(after["pending_settlements"], [])
        book.apply(dict(id="settle-again", type="settle", at="2026-09-09T04:00:01Z"))
        self.assertEqual(book.cash["USD"], D("99"))
        book.apply(dict(id="reuse", type="buy", at="2026-09-09T14:00:00Z", symbol="AAA",
                        quantity=1, price="99", fee_usd="0", usd_to_gbp="0.8"))
        self.assertEqual(book.cash["USD"], 0)

    def test_mixed_due_dates_release_only_eligible_lots(self):
        book = self.book(at="2026-09-08T14:00:00Z", quantity=2)
        self.sell(book, at="2026-09-08T14:01:00Z", due="2026-09-09", identity="sell-1")
        self.sell(book, at="2026-09-09T14:01:00Z", due="2026-09-10", identity="sell-2")
        book.apply(dict(id="settle", type="settle", at="2026-09-10T04:00:00Z"))
        self.assertEqual(book.cash["USD"], D("99"))
        self.assertEqual(book.unsettled, [(date(2026, 9, 10), D("99"))])

    def test_simulator_calculates_date_and_emits_it_in_replayable_sales(self):
        spec = scenario()
        del spec["settles_on"]
        result = run(spec)
        self.assertEqual(result["settles_on"], "2026-09-08")
        self.assertEqual(result["settlement_calendar_id"], SETTLEMENT_CALENDAR_ID)
        sales = [e for e in result["ledger_events"] if e["type"] == "sell"]
        self.assertEqual(len(sales), 1)
        self.assertEqual(sales[0]["settles_on"], "2026-09-08")
        self.assertGreater(result["final_ledger"]["unsettled_usd"], 0)

    def test_simulator_bad_date_errors_even_without_trades_or_partial_output(self):
        with tempfile.TemporaryDirectory() as root:
            path = Path(root)/"scenario.json"
            for due in ("2026-09-07", "2026-09-09", None):
                spec = dict(scenario(), signals=[], settles_on=due)
                path.write_text(json.dumps(spec))
                output, errors = io.StringIO(), io.StringIO()
                with contextlib.redirect_stdout(output), contextlib.redirect_stderr(errors):
                    self.assertEqual(main(["simulate", str(path)]), 2)
                self.assertEqual(output.getvalue(), "")
                self.assertIn("scheduled T+1", errors.getvalue())
