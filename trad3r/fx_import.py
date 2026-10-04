"""Attach a declared Massive connector CSV export to an existing private stock archive."""
import csv
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal, localcontext
import hashlib
from io import BytesIO, StringIO
import json
import os
from pathlib import Path
import re
import tempfile
from zipfile import ZIP_DEFLATED, ZipFile

from .data import decode, load_sample, load_sample_bytes, read_sample_bytes
from .fx import FX_MODEL, completed_fx
from .ledger import nonnegative, positive


def connector_fx(raw, expected_rows, start, end):
    """Parse rendered CSV decimals; never claim recovery of original HTTP number lexemes."""
    first, last = date.fromisoformat(start), date.fromisoformat(end)
    if first.isoformat() != start or last.isoformat() != end or first > last:
        raise ValueError("Invalid declared connector request dates")
    if type(expected_rows) is not int or not 1 <= expected_rows <= 50000:
        raise ValueError("Expected connector row count must be 1 to 50000")
    reader = csv.DictReader(StringIO(raw.decode("utf-8")), strict=True)
    if reader.fieldnames != ["t", "o", "h", "l", "c", "v"]:
        raise ValueError("Connector CSV requires exactly t,o,h,l,c,v in that order")
    result, previous = [], None
    for row in reader:
        if len(result) >= expected_rows or set(row) != set(reader.fieldnames) or any(v is None for v in row.values()):
            raise ValueError("Malformed connector row or row-count mismatch")
        if not re.fullmatch(r"\d{13}", row["t"]):
            raise ValueError("Connector timestamps must be Unix milliseconds")
        stamp = int(row["t"])
        if stamp % 60000 or previous is not None and stamp <= previous:
            raise ValueError("Connector minutes must be aligned, unique and chronological")
        at = datetime(1970, 1, 1, tzinfo=timezone.utc)+timedelta(milliseconds=stamp)
        if not first <= at.date() <= last:
            raise ValueError("Connector record outside declared UTC-date export range")
        o, h, low, close = (positive(row[k]) for k in ("o", "h", "l", "c"))
        volume = nonnegative(row["v"])
        if any(abs(v.adjusted()) > 100 or len(v.as_tuple().digits) > 100 for v in (o, h, low, close, volume)):
            raise ValueError("Connector numeric value exceeds supported precision/range")
        if not low <= min(o, close) <= max(o, close) <= h:
            raise ValueError("Invalid connector OHLC")
        with localcontext() as context:
            context.prec = 28
            rate = Decimal(1)/close
        result.append(dict(bar_start=at.isoformat(), at=(at+timedelta(minutes=1)).isoformat(),
                           gbp_usd_close=str(close), usd_to_gbp=str(rate), model=FX_MODEL))
        previous = stamp
    if len(result) != expected_rows:
        raise ValueError("Connector export row count does not match declared stored-table count")
    normalized = ("\n".join(json.dumps(r, sort_keys=True) for r in result)+"\n").encode()
    completed_fx(normalized)
    return normalized


def attach_connector_fx(stock_path, csv_path, output, *, expected_rows, start, end, retrieved_on):
    output = Path(output)
    if output.exists() or output.is_symlink():
        raise ValueError("Output already exists")
    if date.fromisoformat(retrieved_on).isoformat() != retrieved_on:
        raise ValueError("Retrieval date must be YYYY-MM-DD")
    stock_bytes = read_sample_bytes(stock_path)
    _, source = load_sample_bytes(stock_bytes)
    with csv_path.open("rb") as stream:
        raw = stream.read(20 * 1024 * 1024 + 1)
    if len(raw) > 20 * 1024 * 1024:
        raise ValueError("Connector CSV exceeds 20 MiB limit")
    normalized = connector_fx(raw, expected_rows, start, end)
    metadata = dict(schema="massive-connector-fx-import-v1", ticker="C:GBPUSD",
                    source_stock_archive_sha256=source["source_sha256"], retrieved_on=retrieved_on,
                    request=dict(path=f"/v2/aggs/ticker/C:GBPUSD/range/1/minute/{start}/{end}",
                                 params=dict(adjusted=False, sort="asc", limit=50000)),
                    exported_columns=["t", "o", "h", "l", "c", "v"], expected_rows=expected_rows,
                    csv_sha256=hashlib.sha256(raw).hexdigest(), fx_model=FX_MODEL,
                    research_ready=False,
                    limitations="Caller-declared Massive connector SQL export. CSV is retained as rendered; original HTTP metadata and numeric lexemes unavailable. UTC-date boundaries observed for date-only FX queries. Not an independent vendor signature or executable FX quote.")
    additions = {"GBPUSD_completed_fx.jsonl": normalized, "GBPUSD_connector_export.csv": raw,
                 "fx_import.json": json.dumps(metadata, sort_keys=True, indent=2).encode()}
    with ZipFile(BytesIO(stock_bytes)) as archive:
        if set(additions).intersection(archive.namelist()):
            raise ValueError("Stock archive already contains FX import files; do not replace them")
        manifest = decode(archive.read("manifest.json"))
        if not start <= min(manifest["expected_sessions"]) <= max(manifest["expected_sessions"]) <= end:
            raise ValueError("Declared FX request must span all stock archive sessions")
        payloads = {n: archive.read(n) for n in archive.namelist() if n != "manifest.json"}
    payloads.update(additions)
    manifest["files"] = [dict(file=n, bytes=len(raw), sha256=hashlib.sha256(raw).hexdigest())
                         for n, raw in sorted(payloads.items())]
    if sum(len(r) for r in payloads.values()) > 95 * 1024 * 1024:
        raise ValueError("Combined payload exceeds supported resource limit")
    output.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix=".trad3r-import-", dir=output.parent) as folder:
        temporary = Path(folder)/"combined.zip"
        with ZipFile(temporary, "w", compression=ZIP_DEFLATED) as archive:
            for name, raw in sorted(payloads.items()):
                archive.writestr(name, raw)
            archive.writestr("manifest.json", json.dumps(manifest, sort_keys=True, default=str))
        temporary.chmod(0o600)
        _, combined = load_sample(temporary)
        os.link(temporary, output)
    return dict(mode="offline_connector_fx_import_only", source_stock_archive_sha256=source["source_sha256"],
                combined_sha256=combined["source_sha256"], stock_bars=combined["bars"],
                stock_coverage=combined["coverage"], fx_observations=expected_rows,
                fx_model=FX_MODEL, research_ready=False)
