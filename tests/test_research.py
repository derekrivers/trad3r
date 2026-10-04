import contextlib
import io
import json
from pathlib import Path
import tempfile
import unittest

from trad3r.__main__ import main
from trad3r.research import audit_sample
from test_batches import archive, rows


class ResearchAuditTests(unittest.TestCase):
    def audit(self, days, start, end, transform=lambda x: x):
        with tempfile.TemporaryDirectory() as root:
            path = Path(root)/"sample.zip"
            raw = [row for day in days for row in rows("AAA", day)]
            archive(path, {"AAA": transform(raw)}, days)
            return audit_sample(path, start, end)

    def test_manifest_can_be_complete_while_requested_day_is_absent(self):
        report = self.audit(["2026-09-04", "2026-09-09"], "2026-09-04", "2026-09-09")
        self.assertTrue(report["declared_coverage_complete"])
        self.assertFalse(report["structurally_complete"])
        self.assertEqual(report["window"]["expected_sessions"], 3)
        self.assertEqual(report["sessions_absent_from_manifest"], ["2026-09-08"])
        self.assertEqual(report["requested_coverage"]["missing_bars"], 390)
        self.assertEqual(report["blockers"][0]["code"], "requested_bar_coverage_incomplete")

    def test_missing_edge_dates_are_not_hidden_by_manifest_bounds(self):
        report = self.audit(["2026-09-08"], "2026-09-04", "2026-09-09")
        self.assertEqual(report["sessions_absent_from_manifest"], ["2026-09-04", "2026-09-09"])
        self.assertEqual(report["requested_coverage"]["missing_bars"], 780)

    def test_complete_window_is_not_promoted_to_research_ready(self):
        report = self.audit(["2026-09-04", "2026-09-08"], "2026-09-04", "2026-09-08")
        self.assertTrue(report["structurally_complete"])
        self.assertEqual(report["window"]["expected_sessions"], 2)
        self.assertFalse(report["research_ready"])
        self.assertFalse(report["live_trading_enabled"])
        self.assertEqual(len(report["blockers"]), 5)
        self.assertNotIn("trace", report)

    def test_partial_minutes_and_short_sessions_use_actual_schedule(self):
        report = self.audit(["2026-11-27"], "2026-11-26", "2026-11-29", lambda raw: raw[:-1])
        self.assertEqual(report["window"]["expected_sessions"], 1)
        self.assertEqual(report["requested_coverage"]["expected_bars"], 210)
        self.assertEqual(report["requested_coverage"]["missing_bars"], 1)
        self.assertEqual(report["sessions_absent_from_manifest"], [])

    def test_extra_archive_days_are_not_counted_inside_selected_window(self):
        report = self.audit(["2026-09-04", "2026-09-08"], "2026-09-08", "2026-09-08")
        self.assertEqual(report["selected_bars"], 390)
        self.assertTrue(report["structurally_complete"])

    def test_invalid_or_unsupported_windows_fail(self):
        for start, end in (("2026-09-09", "2026-09-04"), ("2026-09-05", "2026-09-07"),
                           ("20260904", "2026-09-08"), ("2025-12-31", "2026-01-02"),
                           ("2026-12-31", "2027-01-02")):
            with self.subTest(start=start, end=end), self.assertRaises(ValueError):
                self.audit(["2026-09-04"], start, end)

    def test_cli_deterministic_read_only_report_and_no_partial_error_output(self):
        with tempfile.TemporaryDirectory() as root:
            path = Path(root)/"sample.zip"
            archive(path, {"AAA": rows("AAA")}, ["2026-09-04"])
            before = path.read_bytes()
            args = ["research-audit", str(path), "--start", "2026-09-04", "--end", "2026-09-04"]
            outputs = []
            for _ in range(2):
                out = io.StringIO()
                with contextlib.redirect_stdout(out):
                    self.assertEqual(main(args), 0)
                outputs.append(out.getvalue())
            self.assertEqual(outputs[0], outputs[1])
            self.assertEqual(path.read_bytes(), before)
            self.assertEqual(len(json.loads(outputs[0])["source_sha256"]), 64)
            args[-1] = "2027-01-01"
            out = io.StringIO()
            with contextlib.redirect_stdout(out), contextlib.redirect_stderr(io.StringIO()):
                self.assertEqual(main(args), 2)
            self.assertEqual(out.getvalue(), "")
