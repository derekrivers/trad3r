"""Explicit, read-only Massive acquisition; the normal research CLI stays offline."""
import argparse
from datetime import date, datetime, time as day_time, timedelta, timezone
from decimal import Decimal, localcontext
import getpass
import hashlib
from http.client import HTTPException
import json
import os
from pathlib import Path
import re
import sys
import tempfile
import time
from urllib.error import HTTPError, URLError
from urllib.request import HTTPRedirectHandler, Request, build_opener
import warnings
from zipfile import ZIP_DEFLATED, ZipFile
from zoneinfo import ZoneInfo

from .calendar import CALENDAR_ID, scheduled_sessions, session_bounds
from .data import decode, load_sample, parse_bar
from .fx import FX_MODEL

HOST = "https://api.massive.com"
FX_TICKER = "C:GBPUSD"
MAX_RESPONSE = 20 * 1024 * 1024
MAX_PAYLOAD = 95 * 1024 * 1024
PACE_SECONDS = 13


class AcquisitionError(ValueError):
    """Only fixed, credential-free messages cross the acquisition CLI boundary."""


def plan(start, end, symbols, *, today=None):
    sessions = scheduled_sessions(start, end)
    first, last = date.fromisoformat(start), date.fromisoformat(end)
    today = today or datetime.now(ZoneInfo("America/New_York")).date()
    if last >= today or (last-first).days >= 31:
        raise AcquisitionError("Use completed historical dates and at most 31 calendar days per archive")
    symbols = sorted(symbols)
    if not 1 <= len(symbols) <= 10 or len(set(symbols)) != len(symbols) or any(
            not isinstance(s, str) or not re.fullmatch(r"[A-Z][A-Z0-9]{0,9}", s) for s in symbols):
        raise AcquisitionError("Use 1 to 10 unique uppercase alphanumeric stock symbols")
    zone = ZoneInfo("America/New_York")
    first_ms = int(datetime.combine(first, day_time(), zone).timestamp()) * 1000
    last_ms = int(datetime.combine(last+timedelta(days=1), day_time(), zone).timestamp()) * 1000 - 1
    # Explicit instants avoid asset-class differences in date-only query boundaries.
    requests = [dict(ticker=ticker, url=f"{HOST}/v2/aggs/ticker/{ticker}/range/1/minute/"
                     f"{first_ms}/{last_ms}?adjusted=false&sort=asc&limit=50000")
                for ticker in symbols + [FX_TICKER]]
    return dict(schema="massive-acquisition-plan-v2", start=start, end=end, symbols=symbols,
                expected_sessions=sessions, requests=requests, request_count=len(requests),
                minimum_pacing_seconds=(len(requests)-1)*PACE_SECONDS,
                calendar_id=CALENDAR_ID, fx_model=FX_MODEL,
                note="Dry plan has no network or file writes. Existing stock and currency entitlements required; no upgrades.")


class _NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        raise AcquisitionError("Provider redirect refused; no credentials forwarded")


def fetch(url, api_key):
    """One bounded GET. Do not log exception bodies, URLs supplied by a server, or keys."""
    if not re.fullmatch(re.escape(HOST) + r"/v2/aggs/ticker/(?:[A-Z][A-Z0-9]{0,9}|C:GBPUSD)"
                        r"/range/1/minute/\d{13}/\d{13}"
                        r"\?adjusted=false&sort=asc&limit=50000", url):
        raise AcquisitionError("Unexpected acquisition URL")
    if not isinstance(api_key, str) or not 1 <= len(api_key) <= 512 or any(
            not 33 <= ord(c) <= 126 for c in api_key):
        raise AcquisitionError("Missing or invalid local API key")
    request = Request(url, headers={"Authorization": "Bearer " + api_key,
                                   "Accept": "application/json"}, method="GET")
    try:
        with build_opener(_NoRedirect()).open(request, timeout=30) as response:
            if response.status != 200:
                raise AcquisitionError("Unexpected provider HTTP status")
            raw = response.read(MAX_RESPONSE + 1)
        if len(raw) > MAX_RESPONSE:
            raise AcquisitionError("Provider response exceeds resource limit")
        return raw
    except HTTPError as error:
        code = error.code
        error.close()
        if code in (401, 403):
            raise AcquisitionError("Provider denied access; check local key and stock/currency entitlements. No upgrade attempted") from None
        if code == 429:
            raise AcquisitionError("Provider rate limit reached; stop other clients and retry later") from None
        raise AcquisitionError("Provider HTTP request failed; no automatic retry") from None
    except (URLError, OSError, ValueError, HTTPException) as error:
        if isinstance(error, AcquisitionError):
            raise
        raise AcquisitionError("Provider connection failed; no automatic retry") from None


def _json(value):
    """Small deterministic encoder preserving Decimal JSON numbers without float conversion."""
    if isinstance(value, Decimal):
        if not value.is_finite():
            raise AcquisitionError("Nonfinite normalized number")
        return str(value)
    if isinstance(value, dict):
        return "{" + ",".join(json.dumps(k) + ":" + _json(v) for k, v in sorted(value.items())) + "}"
    if isinstance(value, list):
        return "[" + ",".join(_json(v) for v in value) + "]"
    return json.dumps(value, allow_nan=False)


def _number(value):
    if isinstance(value, bool) or not isinstance(value, (int, Decimal)):
        raise AcquisitionError("Invalid aggregate number")
    value = Decimal(value)
    if not value.is_finite() or abs(value.adjusted()) > 100 or len(value.as_tuple().digits) > 100:
        raise AcquisitionError("Invalid aggregate number")
    return value


def normalize(raw, ticker, request_plan):
    """Validate every received bar before retaining RTH stocks or completed FX proxies."""
    try:
        if not isinstance(raw, bytes) or len(raw) > MAX_RESPONSE:
            raise ValueError()
        payload = decode(raw)
        rows = payload.get("results", [])
        if (payload["ticker"] != ticker or payload["status"] != "OK" or payload["adjusted"] is not False
                or payload.get("next_url") or not isinstance(rows, list)
                or type(payload["resultsCount"]) is not int or payload["resultsCount"] != len(rows)
                or not 1 <= len(rows) <= 50000):
            raise ValueError()
        zone = ZoneInfo("America/New_York")
        first = datetime.combine(date.fromisoformat(request_plan["start"]), day_time(), zone)
        last = datetime.combine(date.fromisoformat(request_plan["end"])+timedelta(days=1), day_time(), zone)
        previous, output = None, []
        for row in rows:
            stamp = row["t"]
            if type(stamp) is not int or stamp % 60000:
                raise ValueError()
            at = datetime(1970, 1, 1, tzinfo=timezone.utc) + timedelta(milliseconds=stamp)
            if not first <= at < last or previous is not None and at <= previous:
                raise ValueError()
            previous = at
            o, h, low, c, v = (_number(row[k]) for k in ("o", "h", "l", "c", "v"))
            if min(o, h, low, c) <= 0 or v < 0 or not low <= min(o, c) <= max(o, c) <= h:
                raise ValueError()
            if ticker == FX_TICKER:
                with localcontext() as context:
                    context.prec = 28
                    rate = Decimal(1)/c
                normalized = dict(bar_start=at.isoformat(), at=(at+timedelta(minutes=1)).isoformat(),
                                  gbp_usd_close=str(c), usd_to_gbp=str(rate), model=FX_MODEL)
            else:
                day = at.astimezone(zone).date().isoformat()
                bounds = session_bounds(day)
                if bounds is None or not bounds[0] <= at < bounds[1]:
                    continue
                normalized = dict(symbol=ticker, currency="USD", session_date=day,
                                  timestamp_utc=at.isoformat(), o=o, h=h, l=low, c=c, v=v)
                parse_bar(normalized, ticker)
            output.append(_json(normalized))
        if not output:
            raise ValueError()
        return ("\n".join(output)+"\n").encode()
    except (ValueError, KeyError, TypeError, AttributeError, OverflowError, ArithmeticError, RecursionError):
        raise AcquisitionError("Invalid, empty, adjusted, paginated or inconsistent provider aggregates; archive not published") from None


def download(request_plan, output, api_key, *, fetcher=fetch, sleep=time.sleep):
    # Rebuild URLs from validated fields: caller-supplied request URLs never direct credentials.
    request_plan = plan(request_plan["start"], request_plan["end"], request_plan["symbols"])
    output = Path(output)
    if output.exists() or output.is_symlink():
        raise AcquisitionError("Output already exists; choose a new archive path")
    output.parent.mkdir(parents=True, exist_ok=True)
    files, provenance, total = {}, [], 0
    for index, request in enumerate(request_plan["requests"]):
        if index:
            sleep(PACE_SECONDS)  # Delay after the previous response, even if the network was slow.
        raw = fetcher(request["url"], api_key)
        ticker = request["ticker"]
        name = "GBPUSD_completed_fx.jsonl" if ticker == FX_TICKER else ticker+"_raw_prices_rth.jsonl"
        normalized = normalize(raw, ticker, request_plan)
        total += len(normalized)
        if total > MAX_PAYLOAD:
            raise AcquisitionError("Normalized payload exceeds archive limit; use a smaller window")
        files[name] = normalized
        provenance.append(dict(ticker=ticker, url=request["url"], response_sha256=hashlib.sha256(raw).hexdigest(),
                               response_bytes=len(raw), retained_rows=len(normalized.splitlines())))
    files["acquisition.json"] = _json(dict(schema="massive-acquisition-v1", plan=request_plan,
                                          retrieved_at=datetime.now(timezone.utc).isoformat(),
                                          responses=provenance, research_ready=False,
                                          limitations="Historical corrected aggregates; bar-end availability is a model, not delivery evidence. FX is not a broker execution quote. Missing bars are never filled.")).encode()
    manifest = dict(schema_version=1, provider="Massive", interval="1 minute", symbols=request_plan["symbols"],
                    expected_sessions=request_plan["expected_sessions"],
                    files=[dict(file=name, bytes=len(raw), sha256=hashlib.sha256(raw).hexdigest())
                           for name, raw in sorted(files.items())])
    # Validate the complete temporary archive before an exclusive atomic hard-link publication.
    # A filesystem without hard-link support fails safely; no nonexclusive replace fallback.
    with tempfile.TemporaryDirectory(prefix=".trad3r-acquire-", dir=output.parent) as folder:
        temporary = Path(folder)/"download.zip"
        with ZipFile(temporary, "w", compression=ZIP_DEFLATED) as archive:
            for name, raw in sorted(files.items()):
                archive.writestr(name, raw)
            archive.writestr("manifest.json", _json(manifest))
        temporary.chmod(0o600)
        _, summary = load_sample(temporary)
        os.link(temporary, output)
    return dict(mode="historical_acquisition_only", output=str(output), source_sha256=summary["source_sha256"],
                bars=summary["bars"], coverage=summary["coverage"], fx_model=FX_MODEL, research_ready=False)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--start", required=True)
    parser.add_argument("--end", required=True)
    parser.add_argument("--symbols", nargs="+", required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--download", action="store_true", help="Perform the planned GETs using a local API key")
    args = parser.parse_args(argv)
    try:
        request_plan = plan(args.start, args.end, args.symbols)
        if not args.download:
            print(json.dumps(request_plan, indent=2))
            return 0
        if args.output.exists() or args.output.is_symlink():
            raise AcquisitionError("Output already exists; choose a new archive path")
        key = os.environ.get("MASSIVE_API_KEY")
        if key is None:
            with warnings.catch_warnings():
                warnings.simplefilter("error", getpass.GetPassWarning)
                key = getpass.getpass("Massive API key (hidden, used only for this download): ")
        result = download(request_plan, args.output, key)
        print(json.dumps(result, indent=2))
        return 0
    except AcquisitionError as error:
        print("Acquisition stopped: " + str(error), file=sys.stderr)
    except (OSError, ValueError, EOFError, getpass.GetPassWarning):
        print("Acquisition stopped: check dates, output permissions and secure local key entry", file=sys.stderr)
    except KeyboardInterrupt:
        print("Acquisition cancelled", file=sys.stderr)
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
