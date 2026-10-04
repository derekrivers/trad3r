import contextlib
from datetime import date, datetime, timedelta
from decimal import Decimal as D
import io
from http.client import IncompleteRead
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import Mock, patch
from urllib.error import HTTPError, URLError
from zipfile import ZipFile

from trad3r import acquire as a
from trad3r.data import decode, load_sample
from test_batches import rows


def planned(start="2026-09-04", end="2026-09-04", symbols=("AAA",)):
    return a.plan(start, end, symbols, today=date(2026, 10, 4))


def response(ticker, day="2026-09-04"):
    data = rows("AAA", day)
    if ticker == a.FX_TICKER:
        # Include the minute that completes exactly at the stock opening.
        extra = dict(data[0], timestamp_utc=(datetime.fromisoformat(data[0]["timestamp_utc"])-timedelta(minutes=1)).isoformat())
        data.insert(0, extra)
    aggregates = [dict(t=int(datetime.fromisoformat(r["timestamp_utc"]).timestamp())*1000,
                       **{k: r[k] for k in ("o", "h", "l", "c", "v")}) for r in data]
    if ticker == a.FX_TICKER:
        for r in aggregates:
            r.update(o=D("1.25"), h=D("1.25"), l=D("1.25"), c=D("1.25"))
    return dict(ticker=ticker, adjusted=False, status="OK", resultsCount=len(aggregates), results=aggregates)


def fake_fetch(url, key):
    return a._json(response(a.FX_TICKER if "C:GBPUSD" in url else "AAA")).encode()


class AcquisitionTests(unittest.TestCase):
    def test_plan_is_bounded_canonical_and_has_no_credentials(self):
        p = planned("2026-09-01", "2026-09-30", ("MSFT", "AAPL", "F"))
        self.assertEqual(p["symbols"], ["AAPL", "F", "MSFT"])
        self.assertEqual(p["request_count"], 4)
        self.assertEqual(p["minimum_pacing_seconds"], 39)
        self.assertNotIn("2026-09-07", p["expected_sessions"])
        for r in p["requests"]:
            self.assertTrue(r["url"].endswith("adjusted=false&sort=asc&limit=50000"))
            self.assertNotIn("apiKey", r["url"])
        for start, end in (("2025-09-01", "2025-09-02"), ("2026-09-01", "2026-10-02"),
                           ("2026-10-04", "2026-10-05"), ("2026-09-04", "2026-09-03")):
            with self.assertRaises(ValueError):
                planned(start, end)
        for symbols in ((), ("AAA", "AAA"), ("BRK.B",), ("../AAA",), ("aaa",)):
            with self.assertRaises(ValueError):
                planned(symbols=symbols)

    def test_dry_cli_does_not_access_key_network_or_files(self):
        with tempfile.TemporaryDirectory() as root, patch.object(a, "download") as download, \
                patch.object(a.getpass, "getpass") as prompt, patch.dict(a.os.environ, {}, clear=True):
            path = Path(root)/"absent"/"sample.zip"
            with contextlib.redirect_stdout(io.StringIO()):
                self.assertEqual(a.main(["--start", "2026-09-04", "--end", "2026-09-04",
                                         "--symbols", "AAA", "--output", str(path)]), 0)
            download.assert_not_called()
            prompt.assert_not_called()
            self.assertFalse(path.parent.exists())

    def test_real_format_roundtrip_pacing_decimal_and_fx_causality(self):
        with tempfile.TemporaryDirectory() as root:
            path = Path(root)/"sample.zip"
            sleep = Mock()
            def precise(url, key):
                ticker = a.FX_TICKER if "C:GBPUSD" in url else "AAA"
                result = response(ticker)
                if ticker == "AAA":
                    result["results"][0]["c"] = D("100.1234567890123456789")
                    result["results"][0]["v"] = D("123.45")
                return a._json(result).encode()
            summary = a.download(planned(), path, "private-key", fetcher=precise, sleep=sleep)
            sleep.assert_called_once_with(13)
            self.assertTrue(summary["coverage"]["complete"])
            bars, check = load_sample(path)
            self.assertEqual(check["source_sha256"], summary["source_sha256"])
            self.assertEqual(bars[0].close, D("100.1234567890123456789"))
            self.assertEqual(bars[0].volume, D("123.45"))
            with ZipFile(path) as archive:
                fx = decode(archive.read("GBPUSD_completed_fx.jsonl").splitlines()[0])
                self.assertEqual(fx["at"], bars[0].start.isoformat())
                self.assertEqual(fx["usd_to_gbp"], "0.8")
                for name in archive.namelist():
                    self.assertNotIn(b"private-key", archive.read(name))
                manifest = decode(archive.read("manifest.json"))
                self.assertEqual(len(manifest["files"]), 3)

    def test_regular_hours_filter_respects_early_close_and_dst(self):
        for day, count, opening in (("2026-03-06", 390, "14:30"), ("2026-03-09", 390, "13:30"),
                                    ("2026-11-27", 210, "14:30")):
            payload = response("AAA", day)
            before, after = dict(payload["results"][0]), dict(payload["results"][-1])
            before["t"] -= 60000
            after["t"] += 60000
            payload["results"] = [before]+payload["results"]+[after]
            payload["resultsCount"] += 2
            raw = a.normalize(a._json(payload).encode(), "AAA", dict(start=day, end=day))
            normalized = [decode(line) for line in raw.splitlines()]
            self.assertEqual(len(normalized), count)
            self.assertIn("T"+opening, normalized[0]["timestamp_utc"])

    def test_hidden_prompt_failure_never_starts_download(self):
        with tempfile.TemporaryDirectory() as root, patch.dict(a.os.environ, {}, clear=True), \
                patch.object(a.getpass, "getpass", side_effect=a.getpass.GetPassWarning("private-key")), \
                patch.object(a, "download") as download:
            error = io.StringIO()
            with contextlib.redirect_stderr(error):
                self.assertEqual(a.main(["--start", "2026-09-04", "--end", "2026-09-04", "--symbols", "AAA",
                                         "--output", str(Path(root)/"x.zip"), "--download"]), 2)
            self.assertNotIn("private-key", error.getvalue())
            download.assert_not_called()

    def test_missing_minutes_and_days_stay_missing(self):
        def sparse(url, key):
            result = response(a.FX_TICKER if "C:GBPUSD" in url else "AAA")
            result["results"].pop(5)
            result["resultsCount"] -= 1
            return a._json(result).encode()
        with tempfile.TemporaryDirectory() as root:
            result = a.download(planned(end="2026-09-08"), Path(root)/"x.zip", "key", fetcher=sparse, sleep=Mock())
            self.assertFalse(result["coverage"]["complete"])
            self.assertEqual(result["coverage"]["missing_bars"], 391)

    def test_bad_responses_fail_without_publishing_or_echoing_remote_text(self):
        original = response("AAA")
        cases = [dict(original, adjusted=True), dict(original, ticker="BBB"),
                 dict(original, status="private-key"), dict(original, next_url="https://evil.test/?apiKey=private-key"),
                 dict(original, resultsCount=2), dict(original, results=[]),
                 dict(original, resultsCount=2, results=[original["results"][0]]*2)]
        for field, value in (("c", "private-key"), ("c", True), ("c", D("1e999")),
                             ("t", original["results"][0]["t"]+1), ("h", 90)):
            bad = response("AAA")
            bad["results"][0][field] = value
            cases.append(bad)
        for payload in cases:
            with self.subTest(payload=list(payload)), tempfile.TemporaryDirectory() as root:
                path = Path(root)/"sample.zip"
                with self.assertRaises(a.AcquisitionError) as caught:
                    a.download(planned(), path, "key", fetcher=lambda *_: a._json(payload).encode(), sleep=Mock())
                self.assertNotIn("private-key", str(caught.exception))
                self.assertEqual(list(Path(root).iterdir()), [])

    def test_second_request_failure_never_leaves_a_partial_archive(self):
        with tempfile.TemporaryDirectory() as root:
            path = Path(root)/"sample.zip"
            fetcher = Mock(side_effect=[fake_fetch("AAA", "key"), a.AcquisitionError("denied")])
            with self.assertRaisesRegex(a.AcquisitionError, "denied"):
                a.download(planned(), path, "key", fetcher=fetcher, sleep=Mock())
            self.assertEqual(list(Path(root).iterdir()), [])

    def test_existing_output_and_publish_race_preserve_other_writer(self):
        with tempfile.TemporaryDirectory() as root:
            path = Path(root)/"sample.zip"
            path.write_bytes(b"existing")
            fetcher = Mock()
            with self.assertRaises(a.AcquisitionError):
                a.download(planned(), path, "key", fetcher=fetcher, sleep=Mock())
            fetcher.assert_not_called()
            path.unlink()
            original_link = a.os.link
            def competing(source, target):
                Path(target).write_bytes(b"other writer")
                original_link(source, target)
            with patch.object(a.os, "link", side_effect=competing), self.assertRaises(FileExistsError):
                a.download(planned(), path, "key", fetcher=fake_fetch, sleep=Mock())
            self.assertEqual(path.read_bytes(), b"other writer")
            self.assertEqual(list(Path(root).iterdir()), [path])

    def test_transport_keeps_bearer_out_of_url_and_refuses_redirect(self):
        manager = Mock()
        manager.__enter__ = Mock(return_value=Mock(status=200, read=Mock(return_value=b"{}")))
        manager.__exit__ = Mock(return_value=False)
        opener = Mock(open=Mock(return_value=manager))
        url = planned()["requests"][0]["url"]
        with patch.object(a, "build_opener", return_value=opener):
            self.assertEqual(a.fetch(url, "private-key"), b"{}")
        request = opener.open.call_args.args[0]
        self.assertEqual(request.get_header("Authorization"), "Bearer private-key")
        self.assertNotIn("private-key", request.full_url)
        with self.assertRaises(a.AcquisitionError):
            a._NoRedirect().redirect_request(request, None, 302, "", {}, "https://evil.test")
        for bad_url in ("https://evil.test", url.replace("https:", "http:"), url+"&apiKey=x"):
            with self.assertRaises(a.AcquisitionError):
                a.fetch(bad_url, "private-key")
        for key in ("", "bad\nkey", "has space"):
            with self.assertRaises(a.AcquisitionError):
                a.fetch(url, key)

    def test_http_and_connection_failures_are_redacted_without_retry(self):
        for code in (301, 401, 403, 429, 500):
            error = HTTPError("https://host/?apiKey=private-key", code, "private-key", {}, io.BytesIO(b"private-key"))
            opener = Mock(open=Mock(side_effect=error))
            with patch.object(a, "build_opener", return_value=opener):
                with self.assertRaises(a.AcquisitionError) as caught:
                    a.fetch(planned()["requests"][0]["url"], "private-key")
            self.assertNotIn("private-key", str(caught.exception))
            self.assertEqual(opener.open.call_count, 1)
        for error in (URLError("private-key"), IncompleteRead(b"private-key")):
            with patch.object(a, "build_opener", return_value=Mock(open=Mock(side_effect=error))):
                with self.assertRaisesRegex(a.AcquisitionError, "connection failed"):
                    a.fetch(planned()["requests"][0]["url"], "private-key")

    def test_oversized_response_and_payload_are_rejected(self):
        with patch.object(a, "MAX_RESPONSE", 1), self.assertRaises(a.AcquisitionError):
            a.normalize(fake_fetch("AAA", "key"), "AAA", planned())
        with tempfile.TemporaryDirectory() as root, patch.object(a, "MAX_PAYLOAD", 1):
            path = Path(root)/"x.zip"
            with self.assertRaises(a.AcquisitionError):
                a.download(planned(), path, "key", fetcher=fake_fetch, sleep=Mock())
            self.assertFalse(path.exists())

    def test_mutated_plan_cannot_redirect_the_downloader(self):
        p = planned()
        p["requests"][0]["url"] = "https://evil.test"
        fetcher = Mock(side_effect=fake_fetch)
        with tempfile.TemporaryDirectory() as root:
            a.download(p, Path(root)/"x.zip", "key", fetcher=fetcher, sleep=Mock())
        self.assertTrue(all(c.args[0].startswith(a.HOST+"/") for c in fetcher.call_args_list))
