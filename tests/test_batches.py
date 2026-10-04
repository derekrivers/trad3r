from dataclasses import replace
from datetime import timedelta
import contextlib
import hashlib
import io
import json
from pathlib import Path
import tempfile
import unittest
import zipfile

from trad3r.__main__ import main
from trad3r.batches import completed_batches
from trad3r.calendar import session_bounds
from trad3r.data import coverage_report, load_sample, parse_bar


def rows(symbol, day="2026-09-04"):
    opening, closing = session_bounds(day)
    return [dict(symbol=symbol, currency="USD", session_date=day,
                 timestamp_utc=(opening+timedelta(minutes=i)).isoformat(),
                 o=100, h=101, l=99, c=100, v=1000)
            for i in range(int((closing-opening).total_seconds()//60))]


def archive(path, series, sessions):
    files = {symbol+"_raw_prices_rth.jsonl": ("\n".join(json.dumps(row) for row in data)+"\n").encode()
             for symbol, data in series.items()}
    manifest = dict(schema_version=1, provider="Massive", interval="1 minute",
                    symbols=list(series), expected_sessions=sessions,
                    files=[dict(file=name, bytes=len(raw), sha256=hashlib.sha256(raw).hexdigest())
                           for name, raw in files.items()])
    with zipfile.ZipFile(path, "w") as target:
        for name, raw in files.items():
            target.writestr(name, raw)
        target.writestr("manifest.json", json.dumps(manifest))


class BatchTests(unittest.TestCase):
    def test_complete_regular_and_early_close_grids(self):
        for day, expected in (("2026-09-04", 390), ("2026-11-27", 210)):
            bars = [parse_bar(row, "AAA") for row in rows("AAA", day)]
            report = coverage_report(bars, ["AAA"], [day])
            self.assertTrue(report["complete"])
            self.assertEqual(report["expected_bars"], expected)
            self.assertEqual(report["missing_bars"], 0)

    def test_missing_interior_open_close_and_entire_declared_session_reported(self):
        bars = [parse_bar(row, "AAA") for row in rows("AAA")]
        reduced = bars[1:10] + bars[11:-1]
        report = coverage_report(reduced, ["AAA"], ["2026-09-04", "2026-09-08"])
        self.assertFalse(report["complete"])
        self.assertEqual(report["missing_bars"], 393)
        self.assertEqual(report["sessions"][0]["missing_start_examples"],
                         [bars[i].start.isoformat() for i in (0, 10, 389)])
        self.assertEqual(report["sessions"][1]["observed"], 0)
        self.assertEqual(len(report["sessions"][1]["missing_start_examples"]), 10)

    def test_duplicate_or_unexpected_bars_cannot_satisfy_coverage(self):
        bar = parse_bar(rows("AAA")[0], "AAA")
        for data in ([bar, bar], [replace(bar, symbol="BBB")], [replace(bar, start=bar.start-timedelta(minutes=1))]):
            with self.assertRaises(ValueError):
                coverage_report(data, ["AAA"], ["2026-09-04"])
        for symbols, sessions in (([], ["2026-09-04"]), (["AAA"], []), (["AAA", "AAA"], ["2026-09-04"])):
            with self.assertRaises(ValueError):
                coverage_report([], symbols, sessions)

    def test_batches_are_canonical_and_only_available_after_all_bars_close(self):
        a = [parse_bar(row, "AAA") for row in rows("AAA")[:2]]
        z = [parse_bar(row, "ZZZ") for row in rows("ZZZ")[:2]]
        left = completed_batches([z[0], a[0], a[1], z[1]], ["ZZZ", "AAA"])
        right = completed_batches([a[0], z[0], z[1], a[1]], ["AAA", "ZZZ"])
        self.assertEqual([b.event() for b in left], [b.event() for b in right])
        self.assertEqual(left[0].available_at, a[0].start+timedelta(minutes=1))
        self.assertEqual([b.symbol for b in left[0].bars], ["AAA", "ZZZ"])
        self.assertNotIn(a[1], left[0].bars)
        self.assertEqual(left[0].event()["type"], "bar_batch_closed")

    def test_missing_duplicate_unknown_and_backwards_batches_rejected(self):
        a = [parse_bar(row, "AAA") for row in rows("AAA")[:2]]
        z = [parse_bar(row, "ZZZ") for row in rows("ZZZ")[:2]]
        for data in ([a[0]], [a[0], a[0]], [a[0], replace(z[0], symbol="BAD")],
                     [a[1], z[1], a[0], z[0]], [a[0], z[0], a[1]]):
            with self.assertRaises(ValueError):
                completed_batches(data, ["AAA", "ZZZ"])

    def test_archive_reports_empty_declared_session_and_keeps_sparse_mode(self):
        with tempfile.TemporaryDirectory() as root:
            path = Path(root)/"sample.zip"
            archive(path, {"AAA": rows("AAA")[:1]}, ["2026-09-04", "2026-09-08"])
            bars, summary = load_sample(path)
            self.assertEqual(len(bars), 1)
            self.assertEqual(summary["coverage"]["missing_bars"], 779)
            with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
                self.assertEqual(main(["validate", str(path)]), 0)
                self.assertEqual(main(["validate", str(path), "--require-complete"]), 2)

    def test_strict_replay_rejects_whole_missing_timestamp_before_creating_output(self):
        with tempfile.TemporaryDirectory() as root:
            path, journal = Path(root)/"sample.zip", Path(root)/"events.jsonl"
            series = {s: rows(s) for s in ("AAA", "ZZZ")}
            for data in series.values():
                del data[50]
            archive(path, series, ["2026-09-04"])
            # Batches alone check membership, not completeness of the day.
            bars, summary = load_sample(path)
            self.assertEqual(len(completed_batches(bars, summary["symbols"])), 389)
            with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
                self.assertEqual(main(["replay", str(path), "--journal", str(journal),
                                       "--batches", "--require-complete"]), 2)
            self.assertFalse(journal.exists())

    def test_late_incomplete_batch_creates_no_partial_journal(self):
        with tempfile.TemporaryDirectory() as root:
            path, journal = Path(root)/"sample.zip", Path(root)/"events.jsonl"
            archive(path, {"AAA": rows("AAA")[:2], "ZZZ": rows("ZZZ")[:1]}, ["2026-09-04"])
            with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
                self.assertEqual(main(["replay", str(path), "--journal", str(journal), "--batches"]), 2)
            self.assertFalse(journal.exists())

    def test_strict_batch_journal_is_repeatable_and_preserves_existing_file(self):
        with tempfile.TemporaryDirectory() as root:
            path = Path(root)/"sample.zip"
            archive(path, {"ZZZ": rows("ZZZ"), "AAA": rows("AAA")}, ["2026-09-04"])
            outputs = [Path(root)/"one.jsonl", Path(root)/"two.jsonl"]
            for output in outputs:
                out = io.StringIO()
                with contextlib.redirect_stdout(out):
                    self.assertEqual(main(["replay", str(path), "--journal", str(output),
                                           "--batches", "--require-complete"]), 0)
                report = json.loads(out.getvalue())
                self.assertEqual(report["journal_events"], 390)
                self.assertEqual(report["journal_format"], "completed_batches_v1")
                self.assertEqual(hashlib.sha256(output.read_bytes()).hexdigest(), report["journal_sha256"])
            self.assertEqual(outputs[0].read_bytes(), outputs[1].read_bytes())
            with contextlib.redirect_stderr(io.StringIO()):
                self.assertEqual(main(["replay", str(path), "--journal", str(outputs[0]), "--batches"]), 2)
            self.assertEqual(outputs[0].read_bytes(), outputs[1].read_bytes())
