import contextlib
import hashlib
import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import Mock, patch
from zipfile import ZIP_DEFLATED, ZipFile

from trad3r import acquire, preparation
from trad3r.__main__ import main
from trad3r.data import decode, load_sample_bytes
from trad3r.fx import completed_fx
from trad3r.ledger import utc
from test_acquire import planned, response
from test_backtest import config
from test_batches import archive as stock_archive, rows


def assumptions():
    c = config()
    return dict(schema="fixed-cost-research-assumptions-v1", label="Synthetic fixed-cost fixture, unqualified",
                costs=c["costs"], funding=c["funding"])


def sample(path, days=("2026-09-08", "2026-09-09")):
    def fetcher(url, key):
        ticker = acquire.FX_TICKER if "C:GBPUSD" in url else "AAA"
        payload = response(ticker, days[0])
        payload["results"] = []
        for day in days:
            chunk = response(ticker, day)["results"]
            if ticker == "AAA":
                for r, original in zip(chunk, config(day, count=390)["bars"]):
                    r.update({k: original[k] for k in ("o", "h", "l", "c", "v")})
            payload["results"].extend(chunk)
        payload["resultsCount"] = len(payload["results"])
        return acquire._json(payload).encode()
    acquire.download(planned(days[0], days[-1]), path, "test-key", fetcher=fetcher, sleep=Mock())


def rewrite_fx(path, change):
    with ZipFile(path) as archive:
        files = {name: archive.read(name) for name in archive.namelist() if name != "manifest.json"}
        manifest = decode(archive.read("manifest.json"))
    data = [decode(line) for line in files["GBPUSD_completed_fx.jsonl"].splitlines()]
    files["GBPUSD_completed_fx.jsonl"] = ("\n".join(json.dumps(row) for row in change(data))+"\n").encode()
    manifest["files"] = [dict(file=name, bytes=len(raw), sha256=hashlib.sha256(raw).hexdigest())
                         for name, raw in files.items()]
    with ZipFile(path, "w", compression=ZIP_DEFLATED) as archive:
        for name, raw in files.items():
            archive.writestr(name, raw)
        archive.writestr("manifest.json", json.dumps(manifest))


class PreparationTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.archive = self.root/"sample.zip"
        self.assumptions = self.root/"assumptions.json"
        self.output = self.root/"scenario.json"
        self.assumptions.write_text(json.dumps(assumptions()))
        sample(self.archive)

    def prepare(self, **kwargs):
        return preparation.prepare_baseline(self.archive, self.assumptions, kwargs.get("symbol", "AAA"),
                                            kwargs.get("start", "2026-09-08"), kwargs.get("end", "2026-09-09"))

    def test_preparation_is_deterministic_one_funding_and_has_no_strategy_execution(self):
        with patch("trad3r.__main__.baseline_backtest") as strategy:
            first, second = self.prepare(), self.prepare()
        strategy.assert_not_called()
        self.assertEqual(first, second)
        self.assertEqual([s["session"] for s in first["sessions"]], ["2026-09-08", "2026-09-09"])
        self.assertEqual(sum("funding" in s for s in first["sessions"]), 1)
        self.assertFalse(any("signals" in s or "bars" in s for s in first["sessions"]))
        self.assertEqual(first["sessions"][0]["settles_on"], "2026-09-09")
        self.assertEqual(first["preparation"]["max_fx_age_seconds"], 0)
        self.assertEqual(first["preparation"]["selected_fx_observations"], 302)
        self.assertEqual(first["expected_source_sha256"], hashlib.sha256(self.archive.read_bytes()).hexdigest())

    def test_cli_archive_to_scenario_to_continuous_account(self):
        out = io.StringIO()
        command = ["prepare-baseline", str(self.archive), str(self.assumptions), "--symbol", "AAA",
                   "--start", "2026-09-08", "--end", "2026-09-09", "--output", str(self.output)]
        with contextlib.redirect_stdout(out):
            self.assertEqual(main(command), 0)
        summary = json.loads(out.getvalue())
        self.assertEqual(summary["scenario_sha256"], hashlib.sha256(self.output.read_bytes()).hexdigest())
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            self.assertEqual(main(["baseline-backtest", str(self.output), "--archive", str(self.archive)]), 0)
        result = json.loads(out.getvalue())
        self.assertEqual(result["final_ledger"]["account_pnl_gbp"], "-1.760")
        self.assertEqual(result["evaluation"]["closed_trades"], 2)
        self.assertEqual(result["preparation"]["schema"], preparation.PREPARATION_SCHEMA)
        before = self.output.read_bytes()
        with contextlib.redirect_stderr(io.StringIO()):
            self.assertEqual(main(command), 2)
        self.assertEqual(self.output.read_bytes(), before)

    def test_future_fx_never_backfills_open_and_stale_fx_fails_before_output(self):
        def remove_open(data):
            # First remaining completed observation is 09:31, after first valuation.
            return [r for r in data if utc(r["at"]).isoformat() > "2026-09-08T13:30:00+00:00"]
        rewrite_fx(self.archive, remove_open)
        with self.assertRaisesRegex(ValueError, "Missing or stale.*13:30"):
            self.prepare()
        command = ["prepare-baseline", str(self.archive), str(self.assumptions), "--symbol", "AAA",
                   "--start", "2026-09-08", "--end", "2026-09-09", "--output", str(self.output)]
        out = io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(io.StringIO()):
            self.assertEqual(main(command), 2)
        self.assertFalse(self.output.exists())
        self.assertEqual(out.getvalue(), "")

    def test_one_minute_gap_allowed_but_two_minute_gap_rejected(self):
        rewrite_fx(self.archive, lambda data: [r for r in data if r["at"] != "2026-09-08T14:00:00+00:00"])
        result = self.prepare()
        self.assertEqual(result["preparation"]["max_fx_age_seconds"], 60)
        self.assertFalse(any(r["at"] == "2026-09-08T14:00:00+00:00" for r in result["sessions"][0]["fx"]))
        rewrite_fx(self.archive, lambda data: [r for r in data if r["at"] != "2026-09-08T14:01:00+00:00"])
        with self.assertRaisesRegex(ValueError, "Missing or stale.*14:01"):
            self.prepare()

    def test_bad_fx_direction_timing_model_and_duplicates_fail(self):
        with ZipFile(self.archive) as archive:
            raw = archive.read("GBPUSD_completed_fx.jsonl")
        first = decode(raw.splitlines()[0])
        cases = [dict(first, usd_to_gbp="1.25"), dict(first, model="live-quote"),
                 dict(first, at=first["bar_start"]), dict(first, gbp_usd_close="NaN"),
                 dict(first, at="2026-09-08T09:30:00-04:00"), dict(first, extra="unexpected")]
        for row in cases:
            with self.assertRaises(ValueError):
                completed_fx(json.dumps(row).encode())
        with self.assertRaises(ValueError):
            completed_fx((json.dumps(first)+"\n"+json.dumps(first)).encode())
        with self.assertRaises(ValueError):
            completed_fx(b"")
        for raw in (b"null", b"3", b"[]"):
            with self.assertRaises(ValueError):
                completed_fx(raw)

    def test_wrong_archive_missing_archive_or_other_runner_rejected(self):
        preparation.write_prepared(self.prepare(), self.output)
        with ZipFile(self.archive, "a") as archive:
            archive.comment = b"Different source identity, same bars"
        for command in (["baseline-backtest", str(self.output), "--archive", str(self.archive)],
                        ["baseline-backtest", str(self.output)],
                        ["simulate-series", str(self.output), "--archive", str(self.archive)]):
            out = io.StringIO()
            with contextlib.redirect_stdout(out), contextlib.redirect_stderr(io.StringIO()):
                self.assertEqual(main(command), 2)
            self.assertEqual(out.getvalue(), "")

    def test_missing_dates_symbols_and_invalid_explicit_economics_rejected(self):
        for kwargs in (dict(symbol="BBB"), dict(start="2026-09-04"), dict(end="2026-09-10")):
            with self.assertRaises(ValueError):
                self.prepare(**kwargs)
        for field, values in (("funding", dict(amount="1000", received="1250", fee_gbp="1")),
                              ("funding", dict(amount="0", received="500", fee_gbp="0")),
                              ("costs", dict(entry_fee_usd="-1", exit_fee_usd="0", slippage_usd_per_share="0"))):
            data = assumptions()
            data[field] = values
            self.assumptions.write_text(json.dumps(data))
            with self.assertRaises(ValueError):
                self.prepare()

    def test_source_snapshot_stays_coherent_if_input_path_changes(self):
        original = self.archive.read_bytes()
        def replace_path(raw):
            self.archive.write_bytes(b"Concurrent replacement")
            return load_sample_bytes(raw)
        with patch.object(preparation, "load_sample_bytes", side_effect=replace_path):
            result = self.prepare()
        self.assertEqual(result["expected_source_sha256"], hashlib.sha256(original).hexdigest())
        self.assertEqual(result["preparation"]["selected_fx_observations"], 302)

    def test_stock_only_or_incomplete_archive_rejected_before_output(self):
        data = rows("AAA", "2026-09-08")+rows("AAA", "2026-09-09")
        stock_archive(self.archive, {"AAA": data}, ["2026-09-08", "2026-09-09"])
        with self.assertRaisesRegex(ValueError, "no completed-minute FX"):
            self.prepare()
        stock_archive(self.archive, {"AAA": data[:-1]}, ["2026-09-08", "2026-09-09"])
        with self.assertRaisesRegex(ValueError, "complete declared stock coverage"):
            self.prepare()

    def test_malformed_assumptions_are_a_clean_cli_error(self):
        for field in ("costs", "funding"):
            bad = assumptions()
            bad[field] = list(bad[field])
            self.assumptions.write_text(json.dumps(bad))
            with contextlib.redirect_stderr(io.StringIO()):
                self.assertEqual(main(["prepare-baseline", str(self.archive), str(self.assumptions),
                                       "--symbol", "AAA", "--start", "2026-09-08", "--end", "2026-09-09",
                                       "--output", str(self.output)]), 2)
            self.assertFalse(self.output.exists())
