import contextlib
import csv
from datetime import date, datetime, timezone
from decimal import Decimal as D
import hashlib
import io
import json
from pathlib import Path
import tempfile
import unittest
from zipfile import ZipFile

from trad3r.__main__ import main
from trad3r.acquire import plan
from trad3r.data import decode, load_sample
from trad3r.fx_import import attach_connector_fx, connector_fx
from trad3r.preparation import prepare_baseline
from test_acquire import response
from test_batches import archive, rows
from test_preparation import assumptions


def fx_csv():
    out = io.StringIO(newline="")
    writer = csv.DictWriter(out, fieldnames=["t", "o", "h", "l", "c", "v"], lineterminator="\n")
    writer.writeheader()
    writer.writerows(response("C:GBPUSD")["results"])
    return out.getvalue().encode()


class ConnectorImportTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.stock, self.csv, self.output = (self.root/n for n in ("stocks.zip", "fx.csv", "combined.zip"))
        archive(self.stock, {"AAA": rows("AAA")}, ["2026-09-04"])
        self.csv.write_bytes(fx_csv())
        self.kwargs = dict(expected_rows=391, start="2026-09-04", end="2026-09-04", retrieved_on="2026-10-04")

    def test_combined_archive_preserves_payload_and_provenance_and_prepares(self):
        before = self.stock.read_bytes()
        report = attach_connector_fx(self.stock, self.csv, self.output, **self.kwargs)
        self.assertEqual(self.stock.read_bytes(), before)
        self.assertEqual(report["fx_observations"], 391)
        self.assertTrue(report["stock_coverage"]["complete"])
        self.assertEqual(report["source_stock_archive_sha256"], hashlib.sha256(before).hexdigest())
        self.assertEqual(report["combined_sha256"], hashlib.sha256(self.output.read_bytes()).hexdigest())
        with ZipFile(self.stock) as original, ZipFile(self.output) as combined:
            self.assertEqual(original.read("AAA_raw_prices_rth.jsonl"), combined.read("AAA_raw_prices_rth.jsonl"))
            self.assertEqual(combined.read("GBPUSD_connector_export.csv"), self.csv.read_bytes())
            metadata = decode(combined.read("fx_import.json"))
            self.assertEqual(metadata["csv_sha256"], hashlib.sha256(self.csv.read_bytes()).hexdigest())
            self.assertFalse(metadata["research_ready"])
        economics = self.root/"assumptions.json"
        economics.write_text(json.dumps(assumptions()))
        scenario = prepare_baseline(self.output, economics, "AAA", "2026-09-04", "2026-09-04")
        self.assertEqual(scenario["preparation"]["max_fx_age_seconds"], 0)
        self.assertEqual(scenario["sessions"][0]["fx"][0]["usd_to_gbp"], "0.8")

    def test_incomplete_export_malformed_numbers_and_ohlc_do_not_publish(self):
        raw = fx_csv()
        for corrupted in (raw.replace(b"t,o,h,l,c,v", b"t,o,h,l,c,c"), raw.split(b"\n", 2)[0]+b"\n",
                          raw.replace(b"1.25", b"NaN", 1), raw.replace(b"1.25", b"1.5", 1),
                          raw+b"0,1,1,1,1,1\n", raw+raw.splitlines()[1]+b"\n"):
            self.csv.write_bytes(corrupted)
            with self.assertRaises(ValueError):
                attach_connector_fx(self.stock, self.csv, self.output, **self.kwargs)
            self.assertFalse(self.output.exists())
        with self.assertRaises(ValueError):
            connector_fx(raw, 390, "2026-09-04", "2026-09-04")

    def test_existing_output_and_existing_fx_cannot_be_overwritten(self):
        attach_connector_fx(self.stock, self.csv, self.output, **self.kwargs)
        before = self.output.read_bytes()
        with self.assertRaises(ValueError):
            attach_connector_fx(self.stock, self.csv, self.output, **self.kwargs)
        with self.assertRaisesRegex(ValueError, "already contains FX"):
            attach_connector_fx(self.output, self.csv, self.root/"again.zip", **self.kwargs)
        self.assertEqual(before, self.output.read_bytes())
        self.assertFalse((self.root/"again.zip").exists())

    def test_csv_order_dates_precision_and_timestamp_alignment(self):
        raw = fx_csv()
        header, *lines = raw.splitlines()
        for bad in (b"\n".join([header, *reversed(lines)])+b"\n",
                    raw.replace(lines[0].split(b",")[0], b"1788528540001", 1)):
            with self.assertRaises(ValueError):
                connector_fx(bad, 391, "2026-09-04", "2026-09-04")
        with self.assertRaises(ValueError):
            connector_fx(raw, 391, "2026-09-08", "2026-09-08")
        precise = b"t,o,h,l,c,v\n1788528540000,1.234567890123456789,1.234567890123456789,1.234567890123456789,1.234567890123456789,1\n"
        normalized = decode(connector_fx(precise, 1, "2026-09-04", "2026-09-04"))
        self.assertEqual(normalized["gbp_usd_close"], "1.234567890123456789")
        self.assertEqual(D(normalized["usd_to_gbp"]), D(1)/D(normalized["gbp_usd_close"]))

    def test_cli_and_full_archive_validation(self):
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            self.assertEqual(main(["attach-fx", str(self.stock), str(self.csv), "--expected-rows", "391",
                                   "--start", "2026-09-04", "--end", "2026-09-04", "--retrieved-on", "2026-10-04",
                                   "--output", str(self.output)]), 0)
        report = json.loads(out.getvalue())
        _, loaded = load_sample(self.output)
        self.assertEqual(report["combined_sha256"], loaded["source_sha256"])

    def test_acquisition_uses_same_explicit_et_instants_for_stock_and_fx_across_dst(self):
        p = plan("2026-03-06", "2026-03-09", ["AAA"], today=date(2026, 10, 4))
        self.assertEqual(p["schema"], "massive-acquisition-plan-v2")
        bounds = []
        for request in p["requests"]:
            first, last = request["url"].split("?")[0].split("/")[-2:]
            first, last = int(first), int(last)
            bounds.append((first, last))
            self.assertEqual(datetime.fromtimestamp(first/1000, timezone.utc).isoformat(), "2026-03-06T05:00:00+00:00")
            self.assertEqual(datetime.fromtimestamp((last+1)/1000, timezone.utc).isoformat(), "2026-03-10T04:00:00+00:00")
            self.assertEqual(last % 60000, 59999)
        self.assertEqual(*bounds)
