"""Build engineering scenarios without evaluating the strategy or inventing economics."""
from bisect import bisect_right
from datetime import timedelta
import hashlib
from io import BytesIO
import json
import os
from pathlib import Path
import tempfile
from zipfile import ZipFile

from .calendar import scheduled_sessions, session_bounds
from .data import decode, load_sample_bytes, read_sample_bytes
from .fx import FX_MODEL, completed_fx
from .ledger import Ledger, nonnegative
from .risk import Policy
from .settlement import settlement_date

PREPARATION_SCHEMA = "archive-baseline-preparation-v1"
COST_KEYS = {"entry_fee_usd", "exit_fee_usd", "slippage_usd_per_share"}
FUNDING_KEYS = {"amount", "received", "fee_gbp"}


def prepare_baseline(archive_path, assumptions_path, symbol, start, end):
    expected = scheduled_sessions(start, end)
    source_bytes = read_sample_bytes(archive_path)
    bars, source = load_sample_bytes(source_bytes)
    if not source["coverage"]["complete"] or symbol not in source["symbols"]:
        raise ValueError("Preparation requires complete declared stock coverage and a listed symbol")
    selected = [b for b in bars if b.symbol == symbol and b.session in expected]
    if sorted({b.session for b in selected}) != expected:
        raise ValueError("Archive must cover every requested session")
    with ZipFile(BytesIO(source_bytes)) as archive:
        # load_sample_bytes already checked inventory/digests for this same snapshot.
        if "GBPUSD_completed_fx.jsonl" not in archive.namelist():
            raise ValueError("Archive has no completed-minute FX; obtain the stock/FX acquisition archive")
        observations = completed_fx(archive.read("GBPUSD_completed_fx.jsonl"))
    times = [at for at, _ in observations]
    with assumptions_path.open("rb") as stream:
        assumptions_bytes = stream.read(64 * 1024 + 1)
    if len(assumptions_bytes) > 64 * 1024:
        raise ValueError("Assumptions exceed 64 KiB limit")
    assumptions = decode(assumptions_bytes)
    if (not isinstance(assumptions, dict) or set(assumptions) != {"schema", "label", "costs", "funding"}
            or assumptions["schema"] != "fixed-cost-research-assumptions-v1"
            or not isinstance(assumptions["label"], str) or not 1 <= len(assumptions["label"].strip()) <= 200):
        raise ValueError("Supply labelled fixed-cost research assumptions")
    if (not isinstance(assumptions["costs"], dict) or not isinstance(assumptions["funding"], dict)
            or set(assumptions["costs"]) != COST_KEYS or set(assumptions["funding"]) != FUNDING_KEYS):
        raise ValueError("Explicit costs and initial GBP-to-USD conversion are required")
    costs = {key: str(nonnegative(value)) for key, value in assumptions["costs"].items()}
    funding = {key: str(nonnegative(value)) for key, value in assumptions["funding"].items()}
    at = session_bounds(expected[0])[0].isoformat()
    book = Ledger()
    book.apply(dict(id="prepare-fund", type="fund", at=at, amount=Policy().initial_capital))
    book.apply(dict(id="prepare-conversion", type="exchange", at=at, from_currency="GBP", **funding))
    sessions, maximum_age, selected_count = [], 0, 0
    for index, day in enumerate(expected):
        opening = session_bounds(day)[0]
        # Existing frozen baseline observes each minute boundary from 09:30 to noon.
        required = [opening+timedelta(minutes=i) for i in range(151)]
        indices = set()
        for at in required:
            found = bisect_right(times, at)-1
            age = None if found < 0 else (at-times[found]).total_seconds()
            if age is None or not 0 <= age <= 60:
                raise ValueError("Missing or stale completed FX at " + at.isoformat())
            maximum_age = max(maximum_age, int(age))
            indices.add(found)
        fx = [dict(observations[i][1]) for i in sorted(indices)]
        selected_count += len(fx)
        scenario = dict(symbol=symbol, session=day, settles_on=settlement_date(day).isoformat(),
                        costs=dict(costs), fx=fx)
        if index == 0:
            scenario["funding"] = funding
        sessions.append(scenario)
    return dict(window=dict(start=start, end=end), sessions=sessions,
                expected_source_sha256=source["source_sha256"],
                preparation=dict(schema=PREPARATION_SCHEMA, fx_model=FX_MODEL,
                                 assumptions_sha256=hashlib.sha256(assumptions_bytes).hexdigest(),
                                 assumptions_label=assumptions["label"],
                                 selected_fx_observations=selected_count, max_fx_age_seconds=maximum_age,
                                 research_status="engineering_scenario_only",
                                 limitations="Uniform supplied fixed costs and initial conversion; corrected historical FX proxies. No strategy outcomes inspected, qualified economics or validation verdict."))


def write_prepared(payload, output):
    """Serialize fully before an exclusive atomic publication, never overwrite."""
    raw = (json.dumps(payload, sort_keys=True, indent=2, allow_nan=False)+"\n").encode()
    output = Path(output)
    if output.exists() or output.is_symlink():
        raise ValueError("Prepared output already exists")
    output.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix=".trad3r-prepare-", dir=output.parent) as folder:
        temporary = Path(folder)/"scenario.json"
        temporary.write_bytes(raw)
        temporary.chmod(0o600)
        os.link(temporary, output)
    return dict(mode="offline_baseline_preparation_only", output=str(output), sessions=len(payload["sessions"]),
                scenario_sha256=hashlib.sha256(raw).hexdigest(), source_sha256=payload["expected_source_sha256"],
                preparation=payload["preparation"])
