"""Registered engineering experiments and immutable, inspectable result bundles."""
from dataclasses import asdict
from datetime import datetime, timezone
import hashlib
from io import BytesIO
import json
import os
from pathlib import Path
import platform
import re
import tempfile
from zipfile import ZIP_DEFLATED, ZipFile

from .backtest import baseline_backtest
from .data import decode, load_sample
from .evaluation import summarize_run
from .ledger import replay_ledger, utc
from .preparation import prepare_baseline
from .risk import Policy, money
from .calendar import scheduled_sessions
from .simulation import ROLLOVER_POLICY
from .strategy import STRATEGY_ID

REGISTRATION_SCHEMA = "engineering-experiment-registration-v1"
BUNDLE_SCHEMA = "engineering-experiment-bundle-v1"
PAYLOADS = {"registration.json", "assumptions.json", "scenario.json", "result.json", "summary.json"}


def canonical(value):
    return (json.dumps(value, default=str, sort_keys=True, separators=(",", ":"), allow_nan=False)+"\n").encode()


def digest(raw):
    return hashlib.sha256(raw).hexdigest()


def code_fingerprint():
    """Hash shipped Python sources, including all execution/risk dependencies."""
    root = Path(__file__).parent
    files = {p.name: digest(p.read_bytes()) for p in sorted(root.glob("*.py"))}
    return digest(canonical(files))


def _read(path, limit=64 * 1024):
    with path.open("rb") as stream:
        raw = stream.read(limit+1)
    if len(raw) > limit:
        raise ValueError("Experiment input exceeds resource limit")
    return raw


def _publish(raw, output):
    output = Path(output)
    if output.exists() or output.is_symlink():
        raise ValueError("Experiment output already exists; preserve the original record")
    output.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix=".trad3r-experiment-", dir=output.parent) as folder:
        temporary = Path(folder)/"output"
        temporary.write_bytes(raw)
        temporary.chmod(0o600)
        os.link(temporary, output)


def register_experiment(archive, assumptions, output, *, experiment_id, symbol, start, end):
    if not re.fullmatch(r"[a-z0-9][a-z0-9_-]{0,63}", experiment_id):
        raise ValueError("Experiment ID must be 1 to 64 lowercase letters, digits, underscores or hyphens")
    scenario = prepare_baseline(archive, assumptions, symbol, start, end)
    record = dict(schema=REGISTRATION_SCHEMA, experiment_id=experiment_id, role="engineering",
                  registered_at=datetime.now(timezone.utc).isoformat(),
                  symbol=symbol, window=dict(start=start, end=end), strategy_id=STRATEGY_ID,
                  rollover_policy=ROLLOVER_POLICY, policy=asdict(Policy()),
                  source_sha256=scenario["expected_source_sha256"],
                  assumptions_sha256=scenario["preparation"]["assumptions_sha256"],
                  scenario_sha256=digest(canonical(scenario)), code_sha256=code_fingerprint(),
                  acceptance="Accounting reconciliation, exact inputs and retained halts only; no profitability acceptance threshold.",
                  limitations="Engineering run on inspected data, not an untouched holdout or qualification for paper/live trading. Local records are not authenticated timestamps.")
    raw = canonical(record)
    _publish(raw, output)
    return dict(mode="offline_experiment_registration_only", experiment_id=experiment_id,
                registration_sha256=digest(raw), output=str(output), code_sha256=record["code_sha256"],
                source_sha256=record["source_sha256"], sessions=len(scenario["sessions"]))


def _summary(result, registration, registration_sha):
    def metrics(run):
        return {k: v for k, v in run["evaluation"].items() if k not in ("equity_curve", "trades")}
    return dict(schema=BUNDLE_SCHEMA, experiment_id=registration["experiment_id"], role="engineering",
                registration_sha256=registration_sha, source_sha256=registration["source_sha256"],
                code_sha256=registration["code_sha256"], assumptions_sha256=registration["assumptions_sha256"],
                strategy_id=STRATEGY_ID, policy=registration["policy"], window=registration["window"],
                symbol=registration["symbol"], evaluation=metrics(result),
                cash_reference_evaluation=metrics(result["cash_reference"]), comparison=result["comparison"],
                halt_reasons=result["halt_reasons"], blocked_reasons=result["blocked_reasons"],
                reconciliation="verified", research_ready=False, live_trading_enabled=False)


def _reconcile(result):
    for run in (result, result["cash_reference"]):
        replayed = replay_ledger(run["ledger_events"])
        if canonical(replayed) != canonical(run["final_ledger"]):
            raise ValueError("Experiment ledger does not reconcile")
        if sum(e["type"] == "fund" for e in run["ledger_events"]) != 1:
            raise ValueError("Experiment must fund each counterfactual account exactly once")
        # Persisted Decimal values are strings; compare canonical values and give
        # the metric reconstruction the actual replayed Decimal snapshot.
        if canonical(summarize_run(dict(run, final_ledger=replayed))) != canonical(run["evaluation"]):
            raise ValueError("Experiment metrics do not reconcile")
        latched = set()
        for session in run["sessions"]:
            current = set(session["halt_reasons"])
            if not latched <= current or latched and any(t["type"] == "entry" for t in session["trace"]):
                raise ValueError("Experiment lost a halt or entered during a previously halted session")
            latched = current
        if set(run["halt_reasons"]) != latched:
            raise ValueError("Experiment final halt reasons do not match its sessions")
    difference = (money(result["final_ledger"]["account_pnl_gbp"])
                  - money(result["cash_reference"]["final_ledger"]["account_pnl_gbp"]))
    expected_comparison = dict(reference_id="no-trade-same-cash-v1", net_account_pnl_difference_gbp=difference)
    if canonical(result["comparison"]) != canonical(expected_comparison):
        raise ValueError("Experiment cash comparison does not reconcile")


def _validate_registration(record):
    required = {"schema", "experiment_id", "role", "registered_at", "symbol", "window", "strategy_id",
                "rollover_policy", "policy", "source_sha256", "assumptions_sha256", "scenario_sha256",
                "code_sha256", "acceptance", "limitations"}
    if (not isinstance(record, dict) or set(record) != required or record["schema"] != REGISTRATION_SCHEMA
            or record["role"] != "engineering" or record["strategy_id"] != STRATEGY_ID
            or record["rollover_policy"] != ROLLOVER_POLICY
            or canonical(record["policy"]) != canonical(asdict(Policy()))):
        raise ValueError("Unsupported experiment registration or changed risk/strategy policy")
    if (not isinstance(record["experiment_id"], str)
            or not re.fullmatch(r"[a-z0-9][a-z0-9_-]{0,63}", record["experiment_id"])):
        raise ValueError("Invalid registered experiment ID")
    utc(record["registered_at"])
    for key in ("source_sha256", "assumptions_sha256", "scenario_sha256", "code_sha256"):
        if not isinstance(record[key], str) or not re.fullmatch(r"[0-9a-f]{64}", record[key]):
            raise ValueError("Invalid registered fingerprint")


def run_experiment(registration_path, archive_path, assumptions_path, output):
    output = Path(output)
    if output.exists() or output.is_symlink():
        raise ValueError("Experiment output already exists; do not rerun over an existing result")
    registration_raw = _read(registration_path)
    record = decode(registration_raw)
    _validate_registration(record)
    if record["code_sha256"] != code_fingerprint():
        raise ValueError("Code differs from registration; create a new engineering registration")
    scenario = prepare_baseline(archive_path, assumptions_path, record["symbol"], **record["window"])
    assumptions_raw = _read(assumptions_path)
    if (scenario["expected_source_sha256"] != record["source_sha256"]
            or scenario["preparation"]["assumptions_sha256"] != record["assumptions_sha256"]
            or digest(assumptions_raw) != record["assumptions_sha256"]
            or digest(canonical(scenario)) != record["scenario_sha256"]):
        raise ValueError("Data or assumptions differ from registration")
    bars, source = load_sample(archive_path)
    if source["source_sha256"] != record["source_sha256"]:
        raise ValueError("Archive changed during experiment preparation")
    sessions = [([b for b in bars if b.symbol == s["symbol"] and b.session == s["session"]], s)
                for s in scenario["sessions"]]
    result = baseline_backtest(sessions, **record["window"])
    result.update(preparation=scenario["preparation"], source_sha256=record["source_sha256"],
                  scenario_sha256=record["scenario_sha256"], registration_sha256=digest(registration_raw),
                  runtime=dict(python=platform.python_version(), system=platform.system()),
                  completed_at=datetime.now(timezone.utc).isoformat())
    _reconcile(result)
    summary = _summary(result, record, digest(registration_raw))
    payloads = {"registration.json": registration_raw, "assumptions.json": assumptions_raw,
                "scenario.json": canonical(scenario), "result.json": canonical(result),
                "summary.json": canonical(summary)}
    inventory = dict(schema=BUNDLE_SCHEMA, files=[dict(file=n, bytes=len(raw), sha256=digest(raw))
                                                for n, raw in sorted(payloads.items())])
    target = BytesIO()
    with ZipFile(target, "w", compression=ZIP_DEFLATED) as archive:
        for name, raw in sorted(payloads.items()):
            archive.writestr(name, raw)
        archive.writestr("run_manifest.json", canonical(inventory))
    raw = target.getvalue()
    inspect_bundle_bytes(raw)
    _publish(raw, output)
    return dict(summary, bundle_sha256=digest(raw), output=str(output))


def inspect_bundle_bytes(raw):
    if len(raw) > 50 * 1024 * 1024:
        raise ValueError("Experiment bundle exceeds 50 MiB limit")
    with ZipFile(BytesIO(raw)) as archive:
        members = archive.infolist()
        names = [m.filename for m in members]
        if set(names) != PAYLOADS | {"run_manifest.json"} or len(names) != len(set(names)):
            raise ValueError("Unexpected experiment bundle inventory")
        if sum(m.file_size for m in members) > 100 * 1024 * 1024:
            raise ValueError("Expanded experiment bundle exceeds 100 MiB limit")
        manifest = decode(archive.read("run_manifest.json"))
        entries = manifest["files"]
        if (manifest["schema"] != BUNDLE_SCHEMA or len(entries) != len(PAYLOADS)
                or {e["file"] for e in entries} != PAYLOADS):
            raise ValueError("Unsupported or inconsistent experiment manifest")
        payloads = {n: archive.read(n) for n in PAYLOADS}
        for entry in entries:
            content = payloads[entry["file"]]
            if len(content) != entry["bytes"] or digest(content) != entry["sha256"]:
                raise ValueError("Experiment payload checksum mismatch")
    record, scenario, result, summary = (decode(payloads[n]) for n in
                                         ("registration.json", "scenario.json", "result.json", "summary.json"))
    _validate_registration(record)
    registration_sha = digest(payloads["registration.json"])
    expected_days = scheduled_sessions(**record["window"])
    if (scenario["window"] != record["window"] or result["window"] != record["window"]
            or result["strategy_id"] != record["strategy_id"]
            or result["rollover_policy"] != record["rollover_policy"]
            or result["live_trading_enabled"] is not False
            or result["research_status"] != "engineering_scenario_only"
            or result["cash_reference"]["strategy_id"] != "no-trade-same-cash-v1"):
        raise ValueError("Experiment execution metadata does not match registration")
    for sessions in (scenario["sessions"], result["sessions"], result["cash_reference"]["sessions"]):
        if [s["session"] for s in sessions] != expected_days or any(s["symbol"] != record["symbol"] for s in sessions):
            raise ValueError("Experiment session/symbol inventory does not match registration")
    if utc(result["completed_at"]) < utc(record["registered_at"]):
        raise ValueError("Experiment completion precedes registration")
    if (digest(payloads["assumptions.json"]) != record["assumptions_sha256"]
            or digest(payloads["scenario.json"]) != record["scenario_sha256"]
            or scenario["expected_source_sha256"] != record["source_sha256"]
            or result["source_sha256"] != record["source_sha256"]
            or result["scenario_sha256"] != record["scenario_sha256"]
            or result["registration_sha256"] != registration_sha):
        raise ValueError("Experiment input identities do not reconcile")
    _reconcile(result)
    if canonical(summary) != canonical(_summary(result, record, registration_sha)):
        raise ValueError("Experiment summary does not reconcile")
    return dict(summary, bundle_sha256=digest(raw))


def inspect_experiment(path):
    return inspect_bundle_bytes(_read(path, 50 * 1024 * 1024))
