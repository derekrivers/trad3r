import contextlib
import hashlib
import io
import json
import tempfile
import unittest
import zipfile
from datetime import timedelta
from pathlib import Path
from unittest.mock import patch
from zoneinfo import ZoneInfoNotFoundError

from trad3r.__main__ import main
from trad3r.data import decode, load_sample, parse_bar


def fixture(path, mutate=None, corrupt=False):
    """Synthetic prices only. Never commit licensed vendor data."""
    files = {}
    for symbol in ("ZZZ", "AAA"):
        rows = [{"symbol": symbol, "timestamp_utc": "2026-09-04T13:30:00+00:00",
                 "session_date": "2026-09-04", "currency": "USD",
                 "o": 10, "h": 11, "l": 9, "c": 10.5, "v": 100.25}]
        if mutate:
            mutate(rows)
        raw = ("\n".join(json.dumps(row) for row in rows) + "\n").encode()
        files[symbol + "_raw_prices_rth.jsonl"] = raw
    manifest = {"schema_version": 1, "provider": "Massive", "interval": "1 minute",
                "symbols": ["ZZZ", "AAA"], "expected_sessions": ["2026-09-04"],
                "files": [{"file": n, "bytes": len(v), "sha256": hashlib.sha256(v).hexdigest()}
                          for n, v in files.items()]}
    if corrupt:
        files["AAA_raw_prices_rth.jsonl"] += b" "
    with zipfile.ZipFile(path, "w") as archive:
        for name, value in files.items():
            archive.writestr(name, value)
        archive.writestr("manifest.json", json.dumps(manifest))


class ReplayTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.root = Path(self.directory.name)
        self.archive = self.root / "sample.zip"

    def test_events_are_completed_bars_with_deterministic_symbol_order(self):
        fixture(self.archive)
        bars, summary = load_sample(self.archive)
        self.assertEqual([b.symbol for b in bars], ["AAA", "ZZZ"])
        self.assertEqual(bars[0].available_at - bars[0].start, timedelta(minutes=1))
        self.assertEqual(str(bars[0].volume), "100.25")
        self.assertEqual(summary["bars"], 2)

    def test_checksum_detects_tampered_file(self):
        fixture(self.archive, corrupt=True)
        with self.assertRaisesRegex(ValueError, "Checksum"):
            load_sample(self.archive)

    def test_duplicate_timestamp_rejected(self):
        fixture(self.archive, lambda rows: rows.append(rows[0].copy()))
        with self.assertRaisesRegex(ValueError, "duplicate"):
            load_sample(self.archive)

    def test_invalid_high_rejected(self):
        fixture(self.archive, lambda rows: rows[0].update(h=8))
        with self.assertRaisesRegex(ValueError, "OHLC"):
            load_sample(self.archive)

    def test_naive_timestamp_rejected(self):
        fixture(self.archive, lambda rows: rows[0].update(timestamp_utc="2026-09-04T13:30:00"))
        with self.assertRaisesRegex(ValueError, "UTC"):
            load_sample(self.archive)

    def test_mismatched_session_rejected_before_output(self):
        fixture(self.archive, lambda rows: rows[0].update(timestamp_utc="2026-09-05T13:30:00+00:00"))
        output = self.root / "absent.jsonl"
        with contextlib.redirect_stderr(io.StringIO()):
            self.assertEqual(main(["replay", str(self.archive), "--journal", str(output)]), 2)
        self.assertFalse(output.exists())

    def test_regular_hours_follow_new_york_dst(self):
        for day, opening, closing in (("2026-09-04", "13:30", "19:59"),
                                      ("2026-01-05", "14:30", "20:59")):
            for clock in (opening, closing):
                row = {"symbol": "AAA", "currency": "USD", "session_date": day,
                       "timestamp_utc": f"{day}T{clock}:00+00:00",
                       "o": 10, "h": 11, "l": 9, "c": 10, "v": 100}
                with self.subTest(day=day, clock=clock):
                    self.assertEqual(parse_bar(row, "AAA").session, day)

    def test_outside_hours_and_weekends_rejected(self):
        for day, clock in (("2026-09-04", "13:29"), ("2026-09-04", "20:00"),
                           ("2026-09-04", "23:00"), ("2026-01-05", "14:29"),
                           ("2026-01-05", "21:00"), ("2026-09-05", "13:30")):
            row = {"symbol": "AAA", "currency": "USD", "session_date": day,
                   "timestamp_utc": f"{day}T{clock}:00+00:00",
                   "o": 10, "h": 11, "l": 9, "c": 10, "v": 100}
            with self.subTest(day=day, clock=clock), self.assertRaisesRegex(ValueError, "regular"):
                parse_bar(row, "AAA")

    def test_missing_timezone_data_fails_clearly(self):
        fixture(self.archive)
        with patch("trad3r.data.ZoneInfo", side_effect=ZoneInfoNotFoundError):
            with self.assertRaisesRegex(ValueError, "install tzdata"):
                load_sample(self.archive)

    def test_duplicate_json_keys_and_nonfinite_values_rejected(self):
        for raw in ('{"a":1,"a":2}', '{"a":NaN}'):
            with self.assertRaises(ValueError):
                decode(raw)

    def test_replay_repeatable_and_existing_results_preserved(self):
        fixture(self.archive)
        outputs = [self.root / "one.jsonl", self.root / "two.jsonl"]
        with contextlib.redirect_stdout(io.StringIO()):
            for out in outputs:
                self.assertEqual(main(["replay", str(self.archive), "--journal", str(out)]), 0)
        self.assertEqual(outputs[0].read_bytes(), outputs[1].read_bytes())
        before = outputs[0].read_bytes()
        with contextlib.redirect_stderr(io.StringIO()):
            self.assertEqual(main(["replay", str(self.archive), "--journal", str(outputs[0])]), 2)
        self.assertEqual(outputs[0].read_bytes(), before)

    def test_invalid_input_does_not_create_journal(self):
        fixture(self.archive, corrupt=True)
        output = self.root / "absent.jsonl"
        with contextlib.redirect_stderr(io.StringIO()):
            self.assertEqual(main(["replay", str(self.archive), "--journal", str(output)]), 2)
        self.assertFalse(output.exists())

    def test_corrupt_zip_reports_an_input_error(self):
        self.archive.write_bytes(b"not a ZIP archive")
        with contextlib.redirect_stderr(io.StringIO()):
            self.assertEqual(main(["validate", str(self.archive)]), 2)

    def test_risk_command_reports_halt_without_trading(self):
        path = self.root / "risk.json"
        path.write_text(json.dumps({"current": {"equity": "700"},
                                    "session_start": {"equity": "710"},
                                    "week_start": {"equity": "725"}}))
        stream = io.StringIO()
        with contextlib.redirect_stdout(stream):
            self.assertEqual(main(["risk-check", str(path)]), 0)
        self.assertEqual(json.loads(stream.getvalue())["halt_reasons"], ["daily", "overall", "weekly"])


if __name__ == "__main__":
    unittest.main()
