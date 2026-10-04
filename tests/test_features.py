from dataclasses import replace
from decimal import Decimal as D
import contextlib
import io
import json
from pathlib import Path
import tempfile
import unittest

from trad3r.__main__ import main
from trad3r.batches import CompletedBatch, completed_batches
from trad3r.data import parse_bar
from trad3r.features import FEATURE_SCHEMA, FeatureEngine, feature_snapshots
from test_batches import archive, rows


def bars(count=40, symbol="AAA", day="2026-09-04"):
    data = rows(symbol, day)[:count]
    for i, row in enumerate(data):
        row.update(o=100+i, h=100+i, l=100+i, c=100+i)
    return [parse_bar(row, symbol) for row in data]


class FeatureTests(unittest.TestCase):
    def test_warmup_and_returns_have_explicit_nulls_and_correct_windows(self):
        result = feature_snapshots(bars(6), ["AAA"])
        first = result[0]["rows"][0]
        self.assertIsNone(first["return_1m"])
        self.assertIsNone(first["return_5m"])
        self.assertIsNone(first["sma_5"])
        self.assertIsNone(first["opening_range_high"])
        self.assertEqual(result[4]["rows"][0]["sma_5"], D("102"))
        last = result[5]["rows"][0]
        self.assertEqual(last["return_5m"], D("0.05"))
        self.assertEqual(last["return_1m"], D(105)/104-1)
        self.assertEqual(last["sma_5"], D(103))
        self.assertEqual(last["ohlc_vwap_proxy"], D("102.5"))
        self.assertEqual(result[0]["available_at"], "2026-09-04T13:31:00+00:00")

    def test_volume_ratio_uses_previous_twenty_minutes_excluding_current(self):
        data = bars(21)
        data[-1] = replace(data[-1], volume=D(10000))
        result = feature_snapshots(data, ["AAA"])
        self.assertIsNone(result[19]["rows"][0]["volume_ratio_20"])
        last = result[20]["rows"][0]
        self.assertEqual(last["prior_volume_mean_20"], D(1000))
        self.assertEqual(last["volume_ratio_20"], D(10))
        self.assertEqual(last["cumulative_volume"], D(30000))

    def test_opening_range_is_unavailable_until_1000_then_frozen(self):
        data = bars(31)
        data[-1] = replace(data[-1], high=D(1000), low=D(1))
        result = feature_snapshots(data, ["AAA"])
        self.assertFalse(result[28]["rows"][0]["opening_range_complete"])
        self.assertIsNone(result[28]["rows"][0]["opening_range_low"])
        self.assertEqual(result[29]["available_at"], "2026-09-04T14:00:00+00:00")
        for i in (29, 30):
            self.assertTrue(result[i]["rows"][0]["opening_range_complete"])
            self.assertEqual(result[i]["rows"][0]["opening_range_high"], D(129))
            self.assertEqual(result[i]["rows"][0]["opening_range_low"], D(100))

    def test_future_prices_and_appended_history_do_not_change_past_features(self):
        data = bars()
        prefix = feature_snapshots(data[:15], ["AAA"])
        full = feature_snapshots(data, ["AAA"])
        changed = [bar if i < 15 else replace(bar, open=D(999), high=D(1000), low=D(998), close=D(999))
                   for i, bar in enumerate(data)]
        self.assertEqual(prefix, full[:15])
        self.assertEqual(prefix, feature_snapshots(changed, ["AAA"])[:15])

    def test_sessions_reset_features_and_do_not_invent_overnight_returns(self):
        data = bars() + bars(2, day="2026-09-08")
        result = feature_snapshots(data, ["AAA"])
        row = result[40]["rows"][0]
        self.assertEqual(row["bars_seen"], 1)
        self.assertIsNone(row["return_1m"])
        self.assertIsNone(row["prior_volume_mean_20"])
        self.assertIsNone(row["opening_range_high"])
        self.assertEqual(row["cumulative_volume"], D(1000))

    def test_zero_volume_produces_no_infinite_or_fabricated_vwap_ratio(self):
        data = [replace(bar, volume=D(0)) for bar in bars()]
        row = feature_snapshots(data, ["AAA"])[-1]["rows"][0]
        self.assertEqual(row["prior_volume_mean_20"], 0)
        self.assertIsNone(row["volume_ratio_20"])
        self.assertIsNone(row["ohlc_vwap_proxy"])

    def test_symbol_order_is_canonical_and_features_do_not_mix_symbols(self):
        a, z = bars(6), [replace(b, close=b.close*2, high=b.high*2, low=b.low*2, open=b.open*2)
                        for b in bars(6, symbol="ZZZ")]
        forward = [bar for pair in zip(a, z) for bar in pair]
        reverse = [bar for pair in zip(z, a) for bar in pair]
        result = feature_snapshots(forward, ["AAA", "ZZZ"])
        self.assertEqual(result, feature_snapshots(reverse, ["ZZZ", "AAA"]))
        self.assertEqual([r["sma_5"] for r in result[-1]["rows"]], [D(103), D(206)])

    def test_missing_open_missing_minute_duplicate_and_backwards_rejected(self):
        data = bars()
        for invalid in (data[1:], data[:10]+data[11:], [data[0], data[0]], list(reversed(data))):
            with self.assertRaises(ValueError):
                feature_snapshots(invalid, ["AAA"])

    def test_rejected_batch_does_not_advance_state(self):
        engine = FeatureEngine(["AAA"])
        frames = completed_batches(bars(3), ["AAA"])
        engine.update(frames[0])
        for bad in (frames[2], CompletedBatch((frames[1].bars[0], frames[1].bars[0]))):
            with self.assertRaises(ValueError):
                engine.update(bad)
        self.assertEqual(engine.update(frames[1]), feature_snapshots(bars(2), ["AAA"])[1])

    def test_cli_requires_complete_input_before_creating_features(self):
        with tempfile.TemporaryDirectory() as root:
            path, journal = Path(root)/"sample.zip", Path(root)/"features.jsonl"
            archive(path, {"AAA": rows("AAA")[:40]}, ["2026-09-04"])
            with contextlib.redirect_stderr(io.StringIO()):
                self.assertEqual(main(["features", str(path), "--journal", str(journal)]), 2)
            self.assertFalse(journal.exists())

    def test_cli_is_repeatable_and_identifies_schema_and_source(self):
        with tempfile.TemporaryDirectory() as root:
            path = Path(root)/"sample.zip"
            archive(path, {"AAA": rows("AAA")}, ["2026-09-04"])
            outputs = [Path(root)/"one.jsonl", Path(root)/"two.jsonl"]
            for output in outputs:
                out = io.StringIO()
                with contextlib.redirect_stdout(out):
                    self.assertEqual(main(["features", str(path), "--journal", str(output)]), 0)
                report = json.loads(out.getvalue())
                self.assertEqual(report["feature_schema"], FEATURE_SCHEMA)
                self.assertEqual(report["mode"], "offline_features_only")
                self.assertEqual(report["journal_events"], 390)
                self.assertEqual(len(report["source_sha256"]), 64)
            self.assertEqual(outputs[0].read_bytes(), outputs[1].read_bytes())
            before = outputs[0].read_bytes()
            with contextlib.redirect_stderr(io.StringIO()):
                self.assertEqual(main(["features", str(path), "--journal", str(outputs[0])]), 2)
            self.assertEqual(outputs[0].read_bytes(), before)
