from copy import deepcopy
from datetime import datetime
from decimal import Decimal as D
import contextlib
import io
import json
from pathlib import Path
import tempfile
import unittest

from trad3r.__main__ import main
from trad3r.data import decode, parse_bar
from trad3r.ledger import replay_ledger
from trad3r.simulation import simulate_series
from test_simulation import scenario


def session(day, first=False, fx="0.8"):
    config = scenario()
    delta = datetime.fromisoformat(day) - datetime(2026, 9, 4)
    config["session"] = day
    del config["settles_on"]
    if not first:
        del config["funding"]
    for row in config["bars"]:
        row["session_date"] = day
        row["timestamp_utc"] = (datetime.fromisoformat(row["timestamp_utc"]) + delta).isoformat()
    for row in config["fx"] + config["signals"]:
        row["at"] = (datetime.fromisoformat(row["at"]) + delta).isoformat()
    for row in config["fx"]:
        row["usd_to_gbp"] = fx
    return config


def run(configs):
    configs = decode(json.dumps(configs))
    return simulate_series(([parse_bar(row, config["symbol"]) for row in config["bars"]], config)
                           for config in configs)


class SeriesTests(unittest.TestCase):
    def test_one_funding_one_account_and_replayable_chronological_journal(self):
        configs = [session("2026-09-04", True), session("2026-09-08"), session("2026-09-09")]
        original = deepcopy(configs)
        result = run(configs)
        self.assertEqual(configs, original)
        events = result["ledger_events"]
        self.assertEqual(sum(e["type"] == "fund" for e in events), 1)
        self.assertEqual(sum(e["type"] == "exchange" for e in events), 1)
        self.assertEqual(len({e["id"] for e in events}), len(events))
        self.assertEqual([e["at"] for e in events], sorted(e["at"] for e in events))
        self.assertEqual(replay_ledger(events), result["final_ledger"])
        self.assertEqual(result["final_ledger"]["account_pnl_gbp"], D("-0.96"))
        self.assertEqual(result["baseline_session"], "2026-09-04")
        self.assertEqual(result["baseline_week"], "2026-08-31")
        self.assertFalse(result["live_trading_enabled"])

    def test_pending_cash_carries_then_releases_at_next_supplied_session(self):
        result = run([session("2026-09-04", True), session("2026-09-08"), session("2026-09-09")])
        first, second, third = [s["final_ledger"] for s in result["sessions"]]
        self.assertEqual(first["unsettled_usd"], D("199.4"))
        self.assertEqual(second["unsettled_usd"], first["unsettled_usd"])
        self.assertEqual(second["settled_cash"], first["settled_cash"])
        self.assertEqual(third["unsettled_usd"], 0)
        self.assertEqual(third["settled_cash"]["USD"], D("498.8"))
        self.assertEqual(first["equity_gbp"], third["equity_gbp"])
        self.assertNotIn("ledger_events", result["sessions"][0])

    def test_new_period_blocks_entries_without_replenishing_loss_budget(self):
        result = run([session("2026-09-04", True), session("2026-09-08")])
        first, second = result["sessions"]
        self.assertEqual(second["blocked_reasons"], ["period_review_required"])
        self.assertEqual(second["assessment"]["daily_pnl"], first["assessment"]["daily_pnl"])
        self.assertEqual(second["assessment"]["weekly_pnl"], first["assessment"]["weekly_pnl"])
        self.assertEqual(second["attempts"], 1)
        self.assertFalse(any(e["type"] == "entry" for e in second["trace"]))
        check = next(e for e in second["trace"] if e["type"] == "entry_check")
        self.assertIn("risk_blocked", check["reasons"])
        self.assertIn("period_review_required", check["reasons"])

    def test_fx_losses_while_flat_latch_and_recovery_does_not_clear_halts(self):
        result = run([session("2026-09-04", True), session("2026-09-08", fx="0.1"), session("2026-09-09")])
        self.assertIn("overall", result["sessions"][1]["halt_reasons"])
        self.assertEqual(result["halt_reasons"], ["daily", "overall", "weekly"])
        self.assertEqual(result["final_ledger"]["account_pnl_gbp"], D("-0.96"))
        self.assertIn("period_review_required", result["blocked_reasons"])

    def test_symbol_can_change_only_between_flat_sessions(self):
        second = session("2026-09-08")
        second["symbol"] = "OTHER"
        for row in second["bars"]:
            row["symbol"] = "OTHER"
        result = run([session("2026-09-04", True), second])
        self.assertEqual(result["sessions"][1]["symbol"], "OTHER")
        self.assertIsNone(result["final_ledger"]["position"])

    def test_duplicate_backwards_and_empty_series_rejected(self):
        first = session("2026-09-04", True)
        for configs in ([], [first, first], [session("2026-09-08", True), session("2026-09-04")]):
            with self.assertRaisesRegex(ValueError, "unique and chronological"):
                run(configs)

    def test_later_funding_is_not_silently_ignored(self):
        with self.assertRaisesRegex(ValueError, "first series session"):
            run([session("2026-09-04", True), session("2026-09-08", True)])

    def test_cli_later_failure_has_no_partial_success_output(self):
        with tempfile.TemporaryDirectory() as root:
            path = Path(root)/"series.json"
            later = session("2026-09-08")
            later["fx"] = later["fx"][:1]
            path.write_text(json.dumps({"sessions": [session("2026-09-04", True), later]}))
            out = io.StringIO()
            with contextlib.redirect_stdout(out), contextlib.redirect_stderr(io.StringIO()):
                self.assertEqual(main(["simulate-series", str(path)]), 2)
            self.assertEqual(out.getvalue(), "")

    def test_cli_is_repeatable_and_records_input_hash(self):
        with tempfile.TemporaryDirectory() as root:
            path = Path(root)/"series.json"
            path.write_text(json.dumps({"sessions": [session("2026-09-04", True), session("2026-09-09")]}))
            outputs = []
            for _ in range(2):
                out = io.StringIO()
                with contextlib.redirect_stdout(out):
                    self.assertEqual(main(["simulate-series", str(path)]), 0)
                outputs.append(out.getvalue())
            self.assertEqual(*outputs)
            self.assertEqual(len(json.loads(outputs[0])["scenario_sha256"]), 64)
