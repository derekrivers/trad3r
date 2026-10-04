"""Read validated Massive sample archives without extracting or executing files."""
import hashlib
import json
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from pathlib import Path
from zipfile import ZipFile


def decode(raw):
    def invalid(value):
        raise ValueError("Nonfinite JSON number")
    def unique(pairs):
        result = {}
        for key, value in pairs:
            if key in result:
                raise ValueError("Duplicate JSON key")
            result[key] = value
        return result
    return json.loads(raw, parse_float=Decimal, parse_constant=invalid, object_pairs_hook=unique)


@dataclass(frozen=True)
class Bar:
    symbol: str
    start: datetime
    session: str
    open: Decimal
    high: Decimal
    low: Decimal
    close: Decimal
    volume: Decimal

    @property
    def available_at(self):
        # A completed minute cannot inform a decision at its opening timestamp.
        return self.start + timedelta(minutes=1)

    def event(self):
        return {"type": "bar_closed", "symbol": self.symbol,
                "bar_start": self.start.isoformat(),
                "available_at": self.available_at.isoformat(), "session": self.session,
                **{k: str(getattr(self, k)) for k in ("open", "high", "low", "close", "volume")}}


def parse_bar(row, expected_symbol):
    if row["symbol"] != expected_symbol or row["currency"] != "USD":
        raise ValueError("Unexpected symbol or currency")
    start = datetime.fromisoformat(row["timestamp_utc"])
    if start.tzinfo is None or start.utcoffset() != timedelta(0) or start.second or start.microsecond:
        raise ValueError("Bar timestamp must be minute-aligned UTC")
    session = row["session_date"]
    if datetime.strptime(session, "%Y-%m-%d").date().isoformat() != session:
        raise ValueError("Invalid session date")
    values = []
    for key in ("o", "h", "l", "c", "v"):
        value = row[key]
        if isinstance(value, bool) or not isinstance(value, (int, Decimal)):
            raise ValueError("Invalid numeric bar field")
        value = Decimal(value)
        if not value.is_finite():
            raise ValueError("Nonfinite bar value")
        values.append(value)
    o, h, low, c, volume = values
    if min(o, h, low, c) <= 0 or volume < 0 or not low <= min(o, c) <= max(o, c) <= h:
        raise ValueError("Invalid OHLC or volume")
    return Bar(expected_symbol, start.astimezone(timezone.utc), session, *values)


def load_sample(path: Path):
    if path.stat().st_size > 50 * 1024 * 1024:
        raise ValueError("Sample archive exceeds 50 MiB limit")
    with ZipFile(path) as archive:
        members = archive.infolist()
        names = [m.filename for m in members]
        if len(members) > 1000 or sum(m.file_size for m in members) > 100 * 1024 * 1024:
            raise ValueError("Expanded sample exceeds resource limit")
        if len(names) != len(set(names)) or any("/" in n or "\\" in n for n in names):
            raise ValueError("Duplicate or nested archive member")
        manifest = decode(archive.read("manifest.json"))
        if manifest["schema_version"] != 1 or manifest["provider"] != "Massive" or manifest["interval"] != "1 minute":
            raise ValueError("Unsupported sample format")
        entries = manifest["files"]
        listed = [entry["file"] for entry in entries]
        if len(listed) != len(set(listed)) or "manifest.json" in listed or set(names) != set(listed) | {"manifest.json"}:
            raise ValueError("Manifest inventory mismatch")
        for entry in entries:
            raw = archive.read(entry["file"])
            if len(raw) != entry["bytes"] or hashlib.sha256(raw).hexdigest() != entry["sha256"]:
                raise ValueError("Checksum or size mismatch: " + entry["file"])
        symbols = manifest["symbols"]
        if not symbols or len(symbols) != len(set(symbols)) or any(not isinstance(s, str) or not s.isalnum() for s in symbols):
            raise ValueError("Invalid symbol list")
        sessions = manifest["expected_sessions"]
        if not sessions or sessions != sorted(set(sessions)):
            raise ValueError("Invalid expected sessions")
        bars = []
        counts = {}
        for symbol in symbols:
            name = symbol + "_raw_prices_rth.jsonl"
            # Only raw prices are used. Never double count the adjusted copy.
            series = [parse_bar(decode(line), symbol) for line in archive.read(name).splitlines()]
            times = [bar.start for bar in series]
            if not times or times != sorted(set(times)):
                raise ValueError("Empty, duplicate or unordered bar series")
            if any(bar.session not in sessions for bar in series):
                raise ValueError("Unexpected session")
            counts[symbol] = {s: sum(b.session == s for b in series) for s in sessions}
            bars.extend(series)
    bars.sort(key=lambda b: (b.available_at, b.symbol))
    summary = {"schema_version": 1, "mode": "offline_replay_only",
               "source_sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
               "symbols": sorted(symbols), "bars": len(bars), "session_counts": counts,
               "first_available_at": bars[0].available_at.isoformat(),
               "last_available_at": bars[-1].available_at.isoformat(),
               "checks": "checksums, inventory, schema, OHLC, finite values, ordering",
               "limitations": "No independent price or exchange-calendar validation; no fills or P&L"}
    return bars, summary
