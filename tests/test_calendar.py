import contextlib
from dataclasses import replace
from datetime import datetime, timedelta
import io
import json
from pathlib import Path
import tempfile
import unittest
import zipfile

from trad3r.__main__ import main
from trad3r.admission import check_entry
from trad3r.calendar import CALENDAR_ID, session_bounds, validate_minute
from trad3r.data import decode, load_sample, parse_bar
from trad3r.ledger import Ledger
from trad3r.simulation import simulate
from test_admission import proposal, risk_for, setup_book
from test_replay import fixture
from test_simulation import scenario


class CalendarTests(unittest.TestCase):
    def test_published_holidays_and_weekends_have_no_session(self):
        for day in ("2026-01-01", "2026-01-19", "2026-02-16", "2026-04-03",
                    "2026-05-25", "2026-06-19", "2026-07-03", "2026-09-07",
                    "2026-11-26", "2026-12-25", "2026-07-04", "2026-07-05"):
            with self.subTest(day=day):
                self.assertIsNone(session_bounds(day))

    def test_early_close_final_minute_valid_but_close_minute_rejected(self):
        for day in ("2026-11-27", "2026-12-24"):
            opening, closing = session_bounds(day)
            self.assertEqual(opening.isoformat(), day + "T14:30:00+00:00")
            self.assertEqual(closing.isoformat(), day + "T18:00:00+00:00")
            self.assertEqual((closing - opening).total_seconds() / 60, 210)
            validate_minute(closing - timedelta(minutes=1), day)
            with self.assertRaisesRegex(ValueError, "regular"):
                validate_minute(closing, day)

    def test_no_assumed_july_2_or_bank_holiday_closures(self):
        for day in ("2026-07-02", "2026-10-12", "2026-11-11", "2026-12-31"):
            opening, closing = session_bounds(day)
            self.assertEqual(closing - opening, timedelta(minutes=390))

    def test_dst_changes_use_new_york_not_uk_clock(self):
        for day, clock in (("2026-03-06", "14:30"), ("2026-03-09", "13:30"),
                           ("2026-03-27", "13:30"), ("2026-10-26", "13:30"),
                           ("2026-11-02", "14:30")):
            with self.subTest(day=day):
                self.assertEqual(session_bounds(day)[0].isoformat(), f"{day}T{clock}:00+00:00")

    def test_unknown_years_and_noncanonical_dates_fail_closed(self):
        for day in ("2025-12-31", "2027-01-04", "2026-9-4", "20260904", "2026-W36-5", None):
            with self.subTest(day=day), self.assertRaises(ValueError):
                session_bounds(day)

    def test_bar_holiday_rejected_before_cli_output(self):
        with tempfile.TemporaryDirectory() as root:
            archive, journal = Path(root)/"sample.zip", Path(root)/"journal.jsonl"
            fixture(archive, lambda rows: rows[0].update(session_date="2026-09-07",
                    timestamp_utc="2026-09-07T13:30:00Z"))
            output = io.StringIO()
            errors = io.StringIO()
            with contextlib.redirect_stdout(output), contextlib.redirect_stderr(errors):
                self.assertEqual(main(["replay", str(archive), "--journal", str(journal)]), 2)
            self.assertFalse(journal.exists())
            self.assertEqual(output.getvalue(), "")
            self.assertIn("outside scheduled regular trading hours", errors.getvalue())

    def test_manifest_cannot_declare_closed_or_unsupported_session_without_bars(self):
        with tempfile.TemporaryDirectory() as root:
            archive = Path(root)/"sample.zip"
            for day in ("2026-09-07", "2027-01-04"):
                fixture(archive)
                with zipfile.ZipFile(archive) as source:
                    files = {name: source.read(name) for name in source.namelist()}
                manifest = json.loads(files["manifest.json"])
                manifest["expected_sessions"].append(day)
                files["manifest.json"] = json.dumps(manifest).encode()
                with zipfile.ZipFile(archive, "w") as target:
                    for name, content in files.items():
                        target.writestr(name, content)
                with self.assertRaises(ValueError):
                    load_sample(archive)

    def test_coherent_holiday_entry_rejected_and_early_close_morning_allowed(self):
        _, events = setup_book()
        for day, clock, allowed in (("2026-09-07", "14:00", False),
                                     ("2026-11-27", "15:00", True)):
            at = f"{day}T{clock}:00Z"
            book = Ledger()
            for event in events:
                book.apply(dict(event, at=at))
            risk = dict(risk_for(book), baseline_session=day)
            result = check_entry(book, risk, proposal(quote_at=at, fx_at=at), at, 0)
            self.assertEqual(result["eligible"], allowed)
            self.assertEqual(result["calendar_id"], CALENDAR_ID)
            if not allowed:
                self.assertEqual(result["reasons"], ["market_closed"])

    def test_entry_date_outside_coverage_cannot_be_approved(self):
        book, _ = setup_book()
        with self.assertRaisesRegex(ValueError, "2026 only"):
            check_entry(book, risk_for(book), proposal(), "2027-01-04T15:00:00Z", 0)

    def test_direct_simulator_cannot_bypass_calendar_with_constructed_bars(self):
        spec = decode(json.dumps(scenario()))
        bars = [parse_bar(row, spec["symbol"]) for row in spec["bars"]]
        for day in ("2026-09-07", "2027-01-04"):
            shifted = [replace(bar, start=datetime.fromisoformat(day + "T13:59:00+00:00")
                               + timedelta(minutes=i), session=day) for i, bar in enumerate(bars)]
            with self.assertRaises(ValueError):
                simulate(shifted, dict(spec, session=day))

    def test_calendar_version_is_recorded_in_replay_and_simulation(self):
        with tempfile.TemporaryDirectory() as root:
            archive = Path(root)/"sample.zip"
            fixture(archive)
            self.assertEqual(load_sample(archive)[1]["calendar_id"], CALENDAR_ID)
        spec = decode(json.dumps(scenario()))
        bars = [parse_bar(row, spec["symbol"]) for row in spec["bars"]]
        self.assertEqual(simulate(bars, spec)["calendar_id"], CALENDAR_ID)
