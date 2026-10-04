from copy import deepcopy
from decimal import Decimal as D
import contextlib
import io
import json
from pathlib import Path
import tempfile
import unittest

from trad3r.__main__ import main
from trad3r.backtest import baseline_backtest
from trad3r.data import decode, parse_bar
from trad3r.ledger import replay_ledger
from trad3r.strategy import STRATEGY_ID
from test_batches import archive, rows


def config(day="2026-09-08", first=True, fx="0.8", crossing=True, count=150):
    raw = rows("AAA", day)[:count]
    for i, row in enumerate(raw):
        row.update(o=100, h=101, l=100, c=100)
        if crossing and i >= 30:
            row.update(o=102, h=102, l=102, c=102)
    result = dict(symbol="AAA", session=day, bars=raw,
                  fx=[dict(at=r["timestamp_utc"], usd_to_gbp=fx) for r in raw],
                  costs=dict(entry_fee_usd="0.5", exit_fee_usd="0.5", slippage_usd_per_share="0.05"))
    if first:
        result["funding"] = dict(amount="400", received="500", fee_gbp="0")
    return result


def run(configs, start="2026-09-08", end="2026-09-09"):
    decoded = decode(json.dumps(configs))
    return baseline_backtest([([parse_bar(row, c["symbol"]) for row in c["bars"]], c) for c in decoded], start, end)


class BacktestTests(unittest.TestCase):
    def test_generated_candidates_share_one_account_and_replayable_ledger(self):
        configs = [config(), config("2026-09-09", False)]
        before = deepcopy(configs)
        result = run(configs)
        self.assertEqual(configs, before)
        self.assertEqual(result["strategy_id"], STRATEGY_ID)
        self.assertEqual(result["hypothesis_status"], "unvalidated_hypothesis")
        self.assertEqual(result["final_ledger"]["account_pnl_gbp"], D("-1.76"))
        self.assertEqual(replay_ledger(result["ledger_events"]), result["final_ledger"])
        self.assertEqual(sum(e["type"] == "fund" for e in result["ledger_events"]), 1)
        self.assertEqual([len(s["generated_signals"]) for s in result["sessions"]], [1, 1])
        self.assertTrue(all(not s["truncated_session"] for s in result["sessions"]))
        self.assertEqual(result["missing_sessions"], [])
        self.assertFalse(result["live_trading_enabled"])

    def test_no_candidate_sessions_are_retained(self):
        result = run([config(crossing=False), config("2026-09-09", False)])
        self.assertEqual(result["sessions"][0]["generated_signals"], [])
        self.assertEqual(len(result["sessions"]), 2)
        self.assertEqual(result["final_ledger"]["account_pnl_gbp"], D("-0.88"))

    def test_cost_rejections_do_not_become_missing_or_fabricated_trades(self):
        configs = [config(), config("2026-09-09", False)]
        for c in configs:
            c["costs"]["entry_fee_usd"] = "3"
        result = run(configs)
        self.assertEqual(result["final_ledger"]["account_pnl_gbp"], 0)
        self.assertTrue(all(s["attempts"] == 1 for s in result["sessions"]))
        self.assertTrue(all("trade_loss_limit" in s["trace"][0]["reasons"] for s in result["sessions"]))

    def test_halt_blocks_later_generated_candidates_after_recovery(self):
        result = run([config(), config("2026-09-09", False, fx="0.1"), config("2026-09-10", False)], end="2026-09-10")
        self.assertIn("overall", result["halt_reasons"])
        self.assertEqual([len(s["generated_signals"]) for s in result["sessions"]], [1, 1, 1])
        self.assertFalse(any(e["type"] == "entry" for s in result["sessions"][1:] for e in s["trace"]))

    def test_missing_session_truncation_and_supplied_override_rejected(self):
        complete = [config(), config("2026-09-09", False)]
        for bad in ([complete[0]], [config(count=149), complete[1]],
                    [dict(complete[0], signals=[]), complete[1]], list(reversed(complete))):
            with self.assertRaises(ValueError):
                run(bad)

    def test_symbol_rotation_is_not_silently_treated_as_fixed_hypothesis(self):
        second = config("2026-09-09", False)
        second["symbol"] = "BBB"
        for row in second["bars"]:
            row["symbol"] = "BBB"
        with self.assertRaisesRegex(ValueError, "preselected symbol"):
            run([config(), second])

    def test_cli_determinism_and_rejection_of_strategy_override(self):
        with tempfile.TemporaryDirectory() as root:
            path = Path(root)/"scenario.json"
            payload = dict(window=dict(start="2026-09-08", end="2026-09-09"),
                           sessions=[config(), config("2026-09-09", False)])
            path.write_text(json.dumps(payload))
            outputs = []
            for _ in range(2):
                out = io.StringIO()
                with contextlib.redirect_stdout(out):
                    self.assertEqual(main(["baseline-backtest", str(path)]), 0)
                outputs.append(out.getvalue())
            self.assertEqual(*outputs)
            self.assertEqual(len(json.loads(outputs[0])["scenario_sha256"]), 64)
            payload["strategy_id"] = "different-strategy"
            path.write_text(json.dumps(payload))
            out = io.StringIO()
            with contextlib.redirect_stdout(out), contextlib.redirect_stderr(io.StringIO()):
                self.assertEqual(main(["baseline-backtest", str(path)]), 2)
            self.assertEqual(out.getvalue(), "")

    def test_archive_cli_binds_source_and_requires_complete_declared_grid(self):
        with tempfile.TemporaryDirectory() as root:
            path, sample = Path(root)/"scenario.json", Path(root)/"sample.zip"
            configs = [config(count=390), config("2026-09-09", False, count=390)]
            raw = [row for c in configs for row in c["bars"]]
            archive(sample, {"AAA": raw}, ["2026-09-08", "2026-09-09"])
            for c in configs:
                del c["bars"]
            path.write_text(json.dumps(dict(window=dict(start="2026-09-08", end="2026-09-09"), sessions=configs)))
            out = io.StringIO()
            with contextlib.redirect_stdout(out):
                self.assertEqual(main(["baseline-backtest", str(path), "--archive", str(sample)]), 0)
            self.assertEqual(len(json.loads(out.getvalue())["source_sha256"]), 64)
            archive(sample, {"AAA": raw[:-1]}, ["2026-09-08", "2026-09-09"])
            out = io.StringIO()
            with contextlib.redirect_stdout(out), contextlib.redirect_stderr(io.StringIO()):
                self.assertEqual(main(["baseline-backtest", str(path), "--archive", str(sample)]), 2)
            self.assertEqual(out.getvalue(), "")
