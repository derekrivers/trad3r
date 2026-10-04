from copy import deepcopy
from decimal import Decimal as D
import contextlib
import io
import json
from pathlib import Path
import tempfile
import unittest

from trad3r.__main__ import main
from trad3r.data import parse_bar
from trad3r.strategy import STRATEGY_ID, opening_range_signals
from test_batches import archive, rows


def data(count=40, crossing=30):
    result = rows("AAA")[:count]
    for i, row in enumerate(result):
        row.update(o=100, h=101, l=100, c=100)
        if i >= crossing:
            row.update(o=102, h=102, l=102, c=102)
    return result


def signals(raw):
    return opening_range_signals([parse_bar(row, "AAA") for row in raw], "AAA")["signals"]


def config():
    raw = data()
    return dict(symbol="AAA", session="2026-09-04", bars=raw,
                fx=[dict(at=r["timestamp_utc"], usd_to_gbp="0.8") for r in raw],
                costs=dict(entry_fee_usd="0.5", exit_fee_usd="0.5", slippage_usd_per_share="0.05"),
                funding=dict(amount="400", received="500", fee_gbp="0"))


class StrategyTests(unittest.TestCase):
    def test_first_completed_cross_uses_frozen_range_and_one_share(self):
        result = signals(data())
        self.assertEqual(result, [dict(id=f"{STRATEGY_ID}-2026-09-04-AAA",
                                     at="2026-09-04T14:01:00+00:00", quantity=1,
                                     stop=D(100), target=D(106))])
        self.assertEqual(signals(data(30)), [])

    def test_touch_does_not_cross_and_no_repeat_candidate(self):
        raw = data()
        raw[30].update(o=101, h=101, l=101, c=101)
        raw[33].update(o=100, h=101, l=100, c=100)
        result = signals(raw)
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0]["at"], "2026-09-04T14:02:00+00:00")

    def test_zero_volume_cross_is_not_delayed_into_a_false_cross(self):
        raw = data()
        raw[30]["v"] = 0
        self.assertEqual(signals(raw), [])
        raw[32].update(o=100, h=101, l=100, c=100)
        self.assertEqual(signals(raw)[0]["at"], "2026-09-04T14:04:00+00:00")

    def test_signal_deadline_reserves_full_minute_before_entry_cutoff(self):
        self.assertEqual(signals(data(122, crossing=117))[0]["at"], "2026-09-04T15:28:00+00:00")
        self.assertEqual(signals(data(122, crossing=118)), [])

    def test_future_changes_cannot_change_emitted_candidate(self):
        raw = data()
        prefix = signals(raw[:31])
        for row in raw[31:]:
            row.update(o=900, h=1000, l=1, c=999)
        self.assertEqual(prefix, signals(raw))

    def test_requires_contiguous_single_session_from_open(self):
        raw = data()
        mixed = deepcopy(raw)
        mixed[-1] = rows("AAA", "2026-09-08")[0]
        for bad in ([], raw[1:], raw[:5]+raw[6:], mixed):
            with self.subTest(length=len(bad)), self.assertRaises(ValueError):
                signals(bad)
        with self.assertRaises(ValueError):
            opening_range_signals([parse_bar(raw[0], "AAA")], "BBB")

    def invoke(self, payload, extra=()):
        with tempfile.TemporaryDirectory() as root:
            path = Path(root)/"scenario.json"
            path.write_text(json.dumps(payload))
            out = io.StringIO()
            with contextlib.redirect_stdout(out), contextlib.redirect_stderr(io.StringIO()):
                status = main(["baseline-simulate", str(path), *extra])
            return status, out.getvalue()

    def test_cli_rechecks_costs_at_delayed_fill_and_is_deterministic(self):
        status, output = self.invoke(config())
        self.assertEqual(status, 0)
        self.assertEqual(self.invoke(config())[1], output)
        result = json.loads(output)
        entry = next(e for e in result["trace"] if e["type"] == "entry")
        self.assertEqual(entry["at"], "2026-09-04T14:02:00+00:00")
        self.assertEqual(entry["price"], "102.05")
        self.assertEqual(result["strategy_id"], STRATEGY_ID)
        self.assertEqual(result["research_status"], "engineering_scenario_only")
        self.assertEqual(result["final_ledger"]["account_pnl_gbp"], "-0.880")
        self.assertFalse(result["live_trading_enabled"])
        self.assertTrue(result["truncated_session"])

    def test_gap_or_costs_can_reject_candidate_without_retry(self):
        for cause in ("gap", "costs"):
            payload = config()
            if cause == "gap":
                payload["bars"][32].update(o=104, h=104, l=104, c=104)
            else:
                payload["costs"]["entry_fee_usd"] = "3"
            status, output = self.invoke(payload)
            self.assertEqual(status, 0)
            result = json.loads(output)
            self.assertEqual(result["attempts"], 1)
            self.assertFalse(any(e["type"] == "entry" for e in result["trace"]))
            self.assertIn("trade_loss_limit", result["trace"][0]["reasons"])

    def test_override_and_stale_fx_fail_without_partial_output(self):
        for kind in ("override", "fx"):
            payload = config()
            if kind == "override":
                payload["signals"] = []
            else:
                payload["fx"] = payload["fx"][:1]
            self.assertEqual(self.invoke(payload), (2, ""))

    def test_archive_commands_require_complete_declared_coverage(self):
        with tempfile.TemporaryDirectory() as root:
            path = Path(root)/"sample.zip"
            archive(path, {"AAA": data()}, ["2026-09-04"])
            out = io.StringIO()
            with contextlib.redirect_stdout(out), contextlib.redirect_stderr(io.StringIO()):
                self.assertEqual(main(["strategy-signals", str(path), "--symbol", "AAA", "--session", "2026-09-04"]), 2)
            self.assertEqual(out.getvalue(), "")
            payload = config()
            del payload["bars"]
            self.assertEqual(self.invoke(payload, ["--archive", str(path)]), (2, ""))

    def test_signal_archive_report_identifies_hypothesis_and_source(self):
        with tempfile.TemporaryDirectory() as root:
            path = Path(root)/"sample.zip"
            archive(path, {"AAA": data(390)}, ["2026-09-04"])
            out = io.StringIO()
            with contextlib.redirect_stdout(out):
                self.assertEqual(main(["strategy-signals", str(path), "--symbol", "AAA", "--session", "2026-09-04"]), 0)
            result = json.loads(out.getvalue())
            self.assertEqual(result["research_status"], "unvalidated_hypothesis")
            self.assertEqual(len(result["source_sha256"]), 64)
            self.assertEqual(result["signals"][0]["target"], "106")
