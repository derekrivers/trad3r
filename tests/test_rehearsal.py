import contextlib
import io
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

from trad3r import rehearsal, risk_store
from trad3r.__main__ import main
from trad3r.experiments import canonical, digest
from trad3r.ledger import replay_ledger


class RehearsalTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.directory = Path(self.temp.name)/"drill"

    def test_drill_reconciles_and_fresh_process_retains_all_halts(self):
        report = rehearsal.rehearse_controls(self.directory)
        self.assertTrue(report["passed"])
        self.assertEqual(len(report["checks"]), 17)
        self.assertTrue(all(c["passed"] for c in report["checks"]))
        self.assertFalse(report["paper_ready"])
        self.assertFalse(report["broker_connected"])
        self.assertFalse(report["live_trading_enabled"])
        self.assertEqual(report["generated_orders"], 0)
        journal = (self.directory/"synthetic-ledger-events.json").read_bytes()
        self.assertEqual(report["journal_sha256"], digest(journal))
        events = json.loads(journal)
        self.assertEqual(sum(e["type"] == "fund" for e in events), 1)
        self.assertFalse(any(e["type"] in ("buy", "sell") for e in events))
        self.assertEqual(str(replay_ledger(events)["equity_gbp"]), "1000.0")
        result = subprocess.run([sys.executable, "-m", "trad3r", "risk-status",
                                 str(self.directory/"synthetic-risk.sqlite")], capture_output=True, text=True, timeout=15)
        self.assertEqual(result.returncode, 0, result.stderr)
        persisted = json.loads(result.stdout)
        self.assertEqual(set(persisted["blocked_reasons"]), {"daily", "weekly", "overall", "period_review_required"})
        self.assertEqual(canonical(persisted), canonical(report["final_risk"]))
        self.assertEqual(canonical(report), (self.directory/"rehearsal-report.json").read_bytes())

    def test_existing_directory_is_never_reused_or_reset(self):
        rehearsal.rehearse_controls(self.directory)
        before = {p.name: p.read_bytes() for p in self.directory.iterdir()}
        with self.assertRaises(FileExistsError):
            rehearsal.rehearse_controls(self.directory)
        self.assertEqual(before, {p.name: p.read_bytes() for p in self.directory.iterdir()})
        self.assertTrue(risk_store.status(self.directory/"synthetic-risk.sqlite")["blocked"])

    def test_broken_entry_guard_cannot_publish_success(self):
        original = rehearsal.check_entry
        def bypass(*args, **kwargs):
            result = original(*args, **kwargs)
            result.update(eligible=True, reasons=[])
            return result
        with patch.object(rehearsal, "check_entry", side_effect=bypass), self.assertRaisesRegex(ValueError, "trade_budget_rejected"):
            rehearsal.rehearse_controls(self.directory)
        self.assertFalse((self.directory/"rehearsal-report.json").exists())
        self.assertTrue((self.directory/"synthetic-risk.sqlite").exists())

    def test_failed_halt_persistence_cannot_publish_success(self):
        original = risk_store.status
        def missing_halts(path):
            result = original(path)
            if result["version"] > 1:
                result["assessment"]["halt_reasons"] = []
            return result
        with patch.object(risk_store, "status", side_effect=missing_halts), self.assertRaisesRegex(ValueError, "reopened_store"):
            rehearsal.rehearse_controls(self.directory)
        self.assertFalse((self.directory/"rehearsal-report.json").exists())

    def test_cli_distinguishes_successful_drill_from_trading_readiness(self):
        with contextlib.redirect_stdout(io.StringIO()) as output:
            self.assertEqual(main(["rehearse-controls", str(self.directory)]), 0)
        report = json.loads(output.getvalue())
        self.assertTrue(report["passed"])
        self.assertFalse(report["paper_ready"])
        with contextlib.redirect_stderr(io.StringIO()):
            self.assertEqual(main(["rehearse-controls", str(self.directory)]), 2)
