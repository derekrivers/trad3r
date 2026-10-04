from copy import deepcopy
from datetime import datetime, timedelta
from decimal import Decimal as D
import contextlib
import io
import json
from pathlib import Path
import tempfile
import unittest

from trad3r.data import parse_bar
from trad3r.ledger import replay_ledger
from trad3r.simulation import simulate
from trad3r.__main__ import main


def scenario(start="2026-09-04T13:59:00+00:00", count=6):
    start = datetime.fromisoformat(start)
    rows = [dict(symbol="SYNTH", currency="USD", session_date="2026-09-04",
                 timestamp_utc=(start + timedelta(minutes=i)).isoformat(),
                 o=100, h=100.5, l=99.5, c=100, v=10000) for i in range(count)]
    return dict(symbol="SYNTH", session="2026-09-04", bars=rows,
                fx=[dict(at=r["timestamp_utc"], usd_to_gbp="0.8") for r in rows],
                signals=[dict(id="signal-1", at=(start+timedelta(minutes=1)).isoformat(), quantity=2, stop="99", target="101")],
                costs=dict(entry_fee_usd="0.5", exit_fee_usd="0.5", slippage_usd_per_share="0.05"),
                funding=dict(amount="400", received="500", fee_gbp="0"), settles_on="2026-09-08")


def run(config):
    # Match the CLI's Decimal parsing, not Python's binary float representation.
    from trad3r.data import decode
    config = decode(json.dumps(config, default=str))
    bars = [parse_bar(row, config["symbol"]) for row in config["bars"]]
    return simulate(bars, config)


class SimulationTests(unittest.TestCase):
    def test_signal_waits_one_full_minute_after_availability(self):
        result = run(scenario())
        entry = next(x for x in result["trace"] if x["type"] == "entry")
        self.assertEqual(entry["at"], "2026-09-04T14:01:00+00:00")
        self.assertEqual(entry["price"], D("100.05"))
        self.assertEqual(result["attempts"], 1)
        self.assertFalse(result["live_trading_enabled"])

    def test_ambiguous_stop_target_is_scored_as_stop(self):
        config = scenario()
        config["bars"][2].update(h=102, l=98)
        result = run(config)
        exit = next(x for x in result["trace"] if x["type"] == "exit")
        self.assertEqual(exit["reason"], "stop_ambiguous")
        self.assertEqual(exit["price"], D("98.95"))
        self.assertEqual(result["final_ledger"]["account_pnl_gbp"], D("-2.56"))

    def test_target_trigger_deducts_costs(self):
        config = scenario()
        config["bars"][2].update(h=102, c=101)
        result = run(config)
        self.assertEqual(next(x for x in result["trace"] if x["type"] == "exit")["reason"], "target")
        self.assertEqual(result["final_ledger"]["account_pnl_gbp"], D("0.64"))

    def test_stop_gap_can_exceed_planned_budget_and_latches_daily_stop(self):
        config = scenario()
        config["bars"][3].update(o=90, h=91, l=89, c=90)
        config["signals"].append(dict(id="retry", at="2026-09-04T14:02:00Z", quantity=2, stop="99", target="101"))
        result = run(config)
        exit = next(x for x in result["trace"] if x["type"] == "exit")
        self.assertEqual(exit["reason"], "stop_gap")
        self.assertEqual(exit["price"], D("89.95"))
        self.assertEqual(result["final_ledger"]["account_pnl_gbp"], D("-16.96"))
        self.assertIn("daily", result["halt_reasons"])
        retry = next(x for x in result["trace"] if x.get("signal") == "retry")
        self.assertIn("risk_blocked", retry["reasons"])

    def test_target_gap_gets_no_favourable_price_improvement(self):
        config = scenario()
        config["bars"][3].update(o=105, h=106, l=98, c=100)
        result = run(config)
        exit = next(x for x in result["trace"] if x["type"] == "exit")
        self.assertEqual(exit["reason"], "target_gap")
        self.assertEqual(exit["price"], D("100.95"))

    def test_rejected_entries_consume_attempts(self):
        config = scenario()
        first = config["signals"][0]
        config["signals"] = [dict(first, id=str(i), stop="90" if i < 3 else "99") for i in range(4)]
        result = run(config)
        self.assertEqual(result["attempts"], 4)
        checks = [x for x in result["trace"] if x["type"] == "entry_check"]
        self.assertEqual(len(checks), 4)
        self.assertIn("entry_attempt_limit", checks[-1]["reasons"])
        self.assertFalse(any(x["type"] == "entry" for x in result["trace"]))

    def test_cutoff_and_scheduled_noon_flatten(self):
        cutoff = run(scenario(start="2026-09-04T15:28:00+00:00", count=5))
        check = next(x for x in cutoff["trace"] if x["type"] == "entry_check")
        self.assertIn("outside_entry_window", check["reasons"])
        result = run(scenario(start="2026-09-04T15:26:00+00:00", count=35))
        exit = next(x for x in result["trace"] if x["type"] == "exit")
        self.assertEqual(exit["reason"], "noon_flatten")
        self.assertEqual(exit["at"], "2026-09-04T16:00:00+00:00")
        self.assertIsNone(result["final_ledger"]["position"])
        self.assertFalse(result["truncated_session"])

    def test_short_dataset_is_flagged_and_flattened(self):
        result = run(scenario())
        self.assertTrue(result["truncated_session"])
        self.assertEqual(next(x for x in result["trace"] if x["type"] == "exit")["reason"], "end_of_data")
        self.assertIsNone(result["final_ledger"]["position"])
        self.assertEqual(result["final_ledger"]["account_pnl_gbp"], D("-0.96"))

    def test_gap_changes_cannot_bypass_entry_budget(self):
        config = scenario()
        config["bars"][2].update(o=102, h=103, l=101.5, c=102)
        result = run(config)
        check = next(x for x in result["trace"] if x["type"] == "entry_check")
        self.assertIn("gap_invalidates_bracket", check["reasons"])
        config["signals"][0]["target"] = "110"
        result = run(config)
        self.assertIn("trade_loss_limit", next(x for x in result["trace"] if x["type"] == "entry_check")["reasons"])

    def test_future_fx_is_not_used_for_earlier_entry(self):
        config = scenario()
        before = run(config)
        config["fx"][-1]["usd_to_gbp"] = "0.9"
        after = run(config)
        self.assertEqual([x for x in before["trace"] if x["type"] in ("entry", "entry_check")],
                         [x for x in after["trace"] if x["type"] in ("entry", "entry_check")])

    def test_fx_risk_halt_closes_at_next_open_and_survives_recovery(self):
        config = scenario()
        config["fx"][3]["usd_to_gbp"] = "0.77"
        result = run(config)
        exit = next(x for x in result["trace"] if x["type"] == "exit")
        self.assertEqual(exit["reason"], "risk_halt")
        self.assertEqual(exit["at"], "2026-09-04T14:02:00+00:00")
        self.assertEqual(exit["price"], D("99.95"))
        self.assertIsNone(result["final_ledger"]["position"])
        self.assertIn("daily", result["halt_reasons"])
        self.assertEqual(result["final_ledger"]["account_pnl_gbp"], D("-0.96"))

    def test_stale_fx_gaps_duplicates_and_unknown_signal_times_rejected(self):
        for kind in ("fx", "gap", "duplicate", "signal"):
            config = scenario()
            if kind == "fx":
                config["fx"] = config["fx"][:1]
            elif kind == "gap":
                del config["bars"][3]
            elif kind == "duplicate":
                config["signals"].append(deepcopy(config["signals"][0]))
            else:
                config["signals"][0]["at"] = "2026-09-04T14:00:30Z"
            with self.subTest(kind=kind), self.assertRaises(ValueError):
                run(config)

    def test_final_signal_expires_and_never_fills_retroactively(self):
        config = scenario(count=2)
        result = run(config)
        self.assertEqual(result["attempts"], 0)
        self.assertEqual(result["trace"][0]["type"], "expired_signal")

    def test_output_ledger_is_replayable_and_cli_deterministic(self):
        config = scenario()
        result = run(config)
        self.assertEqual(replay_ledger(result["ledger_events"]), result["final_ledger"])
        with tempfile.TemporaryDirectory() as root:
            path = Path(root) / "scenario.json"
            path.write_text(json.dumps(config))
            outputs = []
            for _ in range(2):
                out = io.StringIO()
                with contextlib.redirect_stdout(out):
                    self.assertEqual(main(["simulate", str(path)]), 0)
                outputs.append(out.getvalue())
            self.assertEqual(outputs[0], outputs[1])

    def test_archive_cli_filters_symbol_and_records_provenance(self):
        from test_replay import fixture
        with tempfile.TemporaryDirectory() as root:
            root = Path(root)
            archive, path = root/"sample.zip", root/"scenario.json"
            fixture(archive)
            config = scenario()
            del config["bars"]
            config.update(symbol="AAA", signals=[], fx=[dict(at="2026-09-04T13:30:00Z", usd_to_gbp="0.8")])
            path.write_text(json.dumps(config))
            out = io.StringIO()
            with contextlib.redirect_stdout(out):
                self.assertEqual(main(["simulate", str(path), "--archive", str(archive)]), 0)
            result = json.loads(out.getvalue())
            self.assertEqual(result["bars"], 1)
            self.assertEqual(result["symbol"], "AAA")
            self.assertEqual(len(result["source_sha256"]), 64)
            self.assertEqual(len(result["scenario_sha256"]), 64)

    def test_cli_bad_fx_prints_no_partial_success_report(self):
        with tempfile.TemporaryDirectory() as root:
            path = Path(root)/"scenario.json"
            config = scenario()
            config["fx"] = config["fx"][:1]
            path.write_text(json.dumps(config))
            out = io.StringIO()
            with contextlib.redirect_stdout(out), contextlib.redirect_stderr(io.StringIO()):
                self.assertEqual(main(["simulate", str(path)]), 2)
            self.assertEqual(out.getvalue(), "")
