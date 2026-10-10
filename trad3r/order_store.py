"""Atomic synthetic order admission; no adapter, dispatch, fill, or live mode."""
from contextlib import contextmanager
from dataclasses import asdict
from datetime import time, timedelta
from decimal import Decimal as D
import hashlib
import json
import os
from pathlib import Path
import re
import sqlite3
from zoneinfo import ZoneInfo

from .calendar import CALENDAR_ID, session_bounds
from .data import decode
from .ledger import shares, utc
from .risk import Mark, Policy, assess, money, planned_long_loss


APP_ID = 0x54524434
DATABASE_VERSION = 3
REDUCING_DATABASE_VERSION = 4
SUPPORTED_DATABASE_VERSIONS = {1, 2, 3, 4}
ACCOUNT_SCHEMA = "synthetic-order-account-v1"
STATE_SCHEMA = "order-account-state-v1"
ADMISSION_SCHEMA = "order-admission-v1"
MODE = "synthetic_order_admission_only"
MAX_ATTEMPTS = 3
MAX_EXPOSURE_GBP = D("500")
MAX_FRESHNESS = timedelta(seconds=60)

SNAPSHOT_FIELDS = {
    "schema", "account_id", "environment", "at", "settled_cash_usd",
    "position_quantity", "mark", "session_start", "week_start",
    "ledger_version", "risk_version", "evidence_version", "halt_reasons",
}
PROPOSAL_FIELDS = {
    "schema", "account_id", "environment", "intent_id", "candidate_id",
    "client_order_id", "decision_at", "expires_at", "expected_account_version",
    "expected_ledger_version", "expected_risk_version", "expected_evidence_version",
    "expected_policy_sha256", "instrument_id", "symbol", "currency", "side", "purpose", "quantity",
    "order_type", "time_in_force", "limit_price_usd", "stop_price_usd",
    "entry_fee_usd", "exit_fee_usd", "slippage_usd_per_share", "usd_to_gbp",
    "quote_at", "fx_at",
}


def pack(value):
    return json.dumps(value, default=str, sort_keys=True, separators=(",", ":"))


def digest(value):
    return hashlib.sha256(pack(value).encode()).hexdigest()


def _identity(value, label):
    if not isinstance(value, str) or not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._:-]{0,127}", value):
        raise ValueError(f"Invalid {label}")
    return value


def _version(value, label):
    if type(value) is not int or value < 0:
        raise ValueError(f"{label} must be a nonnegative integer")
    return value


def _decimal_string(value, label, *, allow_zero=True, allow_negative=False):
    if (not isinstance(value, str) or len(value) > 128
            or not re.fullmatch(r"-?(?:0|[1-9]\d*)(?:\.\d+)?", value)):
        raise ValueError(f"{label} must be a decimal string")
    result = money(value)
    if (not allow_negative and result < 0) or not allow_zero and result == 0:
        raise ValueError(f"Invalid {label}")
    return result


def _timestamp_string(value, label):
    if not isinstance(value, str):
        raise ValueError(f"{label} must be a UTC timestamp string")
    return utc(value)


def _mark(value):
    if not isinstance(value, dict) or set(value) != {"equity", "deposits", "withdrawals"}:
        raise ValueError("Mark requires equity and cumulative deposits/withdrawals")
    _decimal_string(value["equity"], "equity", allow_negative=True)
    _decimal_string(value["deposits"], "deposits")
    _decimal_string(value["withdrawals"], "withdrawals")
    return Mark(**value)


def _mark_payload(value):
    return {key: str(item) for key, item in asdict(value).items()}


def _policy_payload():
    return {key: str(value) for key, value in asdict(Policy()).items()}


def _periods(at):
    local = utc(at).astimezone(ZoneInfo("America/New_York")).date()
    return local.isoformat(), (local - timedelta(days=local.weekday())).isoformat()


@contextmanager
def database(path, write=False):
    uri = Path(path).resolve().as_uri() + ("?mode=rw" if write else "?mode=ro")
    connection = sqlite3.connect(uri, uri=True, timeout=3, isolation_level=None)
    try:
        connection.execute("PRAGMA synchronous=FULL")
        if connection.execute("PRAGMA application_id").fetchone()[0] != APP_ID:
            raise ValueError("Not a Trad3r order database")
        if connection.execute("PRAGMA user_version").fetchone()[0] not in SUPPORTED_DATABASE_VERSIONS:
            raise ValueError("Unsupported order database version")
        if connection.execute("PRAGMA quick_check").fetchone()[0] != "ok":
            raise ValueError("Order database integrity check failed")
        connection.execute("BEGIN IMMEDIATE" if write else "BEGIN")
        yield connection
        connection.commit()
    except BaseException:
        connection.rollback()
        raise
    finally:
        connection.close()


def _parse_state(raw):
    state = decode(raw)
    required = {
        "schema", "version", "policy", "calendar_id", "account_id", "environment",
        "at", "session", "week", "settled_cash_usd", "position_quantity", "mark",
        "session_start", "week_start", "ledger_version", "risk_version",
        "evidence_version", "halt_reasons", "attempts", "reserved_cash_usd",
        "reserved_exposure_gbp", "reserved_loss_gbp", "unresolved_reasons",
        "live_trading_enabled",
    }
    if not isinstance(state, dict) or set(state) != required or state["schema"] != STATE_SCHEMA:
        raise ValueError("Invalid stored order state")
    if state["policy"] != _policy_payload() or state["calendar_id"] != CALENDAR_ID:
        raise ValueError("Stored order policy or calendar differs; explicit migration required")
    if state["environment"] != "synthetic" or state["live_trading_enabled"] is not False:
        raise ValueError("Order store is not synthetic and disarmed")
    _identity(state["account_id"], "account id")
    for field in ("version", "ledger_version", "risk_version", "evidence_version", "attempts"):
        _version(state[field], field.replace("_", " "))
    if state["attempts"] > MAX_ATTEMPTS:
        raise ValueError("Stored entry attempts exceed the limit")
    at = _timestamp_string(state["at"], "stored account time")
    if _periods(at.isoformat()) != (state["session"], state["week"]):
        raise ValueError("Stored order periods are inconsistent")
    settled = _decimal_string(state["settled_cash_usd"], "settled cash")
    position = state["position_quantity"]
    if type(position) is not int or position < 0:
        raise ValueError("Invalid stored position quantity")
    mark, session_start, week_start = map(
        _mark, (state["mark"], state["session_start"], state["week_start"])
    )
    if not isinstance(state["halt_reasons"], list) or len(state["halt_reasons"]) != len(set(state["halt_reasons"])):
        raise ValueError("Invalid stored halt reasons")
    assessment = assess(mark, session_start, week_start, tuple(state["halt_reasons"]))
    if list(assessment.halt_reasons) != state["halt_reasons"]:
        raise ValueError("Stored halt reasons are incomplete or unordered")
    for field in ("reserved_cash_usd", "reserved_exposure_gbp", "reserved_loss_gbp"):
        _decimal_string(state[field], field.replace("_", " "))
    if money(state["reserved_cash_usd"]) > settled:
        raise ValueError("Stored cash reservations exceed settled cash")
    if not isinstance(state["unresolved_reasons"], list) or state["unresolved_reasons"] != sorted(set(state["unresolved_reasons"])):
        raise ValueError("Invalid unresolved order reasons")
    return state


def _record_payload(raw):
    value = decode(raw)
    required = {
        "intent_id", "candidate_id", "client_order_id", "proposal_sha256", "proposal",
        "state", "attempt_consumed", "reasons", "reservation", "committed_version",
    }
    if not isinstance(value, dict) or set(value) != required:
        raise ValueError("Invalid stored intent record")
    if value["state"] not in ("reserved", "rejected") or type(value["attempt_consumed"]) is not bool:
        raise ValueError("Invalid stored admission outcome")
    if not isinstance(value["reasons"], list) or value["reasons"] != sorted(set(value["reasons"])):
        raise ValueError("Invalid stored admission reasons")
    for field in ("intent_id", "candidate_id", "client_order_id"):
        _identity(value[field], field.replace("_", " "))
    if value["proposal_sha256"] != digest(value["proposal"]):
        raise ValueError("Stored proposal digest mismatch")
    _version(value["committed_version"], "committed version")
    if value["state"] == "reserved":
        if value["reasons"] or not value["attempt_consumed"] or not isinstance(value["reservation"], dict):
            raise ValueError("Invalid accepted reservation")
        if set(value["reservation"]) != {"cash_usd", "exposure_gbp", "planned_loss_gbp", "expires_at"}:
            raise ValueError("Invalid reservation fields")
        for field in ("cash_usd", "exposure_gbp", "planned_loss_gbp"):
            _decimal_string(value["reservation"][field], field.replace("_", " "), allow_zero=False)
        _timestamp_string(value["reservation"]["expires_at"], "stored expiry")
    elif value["reservation"] is not None or not value["reasons"]:
        raise ValueError("Invalid rejected reservation")
    return value


def _release_payload(raw):
    value = decode(raw)
    if (not isinstance(value, dict) or set(value) != {
            "intent_id", "reason", "at", "committed_version"}
            or value["reason"] != "expired_authority"):
        raise ValueError("Invalid stored reservation release")
    _identity(value["intent_id"], "released intent id")
    _timestamp_string(value["at"], "release time")
    _version(value["committed_version"], "release committed version")
    return value


def _adjustment_payload(raw):
    value = decode(raw)
    required = {
        "reconciliation_id", "snapshot_id", "intent_id", "at", "settled_cash_usd",
        "position_quantity", "mark", "halt_reasons", "reserved_cash_usd",
        "reserved_exposure_gbp", "reserved_loss_gbp", "committed_version",
    }
    if not isinstance(value, dict) or set(value) != required:
        raise ValueError("Invalid stored reconciliation adjustment")
    for field in ("reconciliation_id", "snapshot_id"):
        _identity(value[field], field.replace("_", " "))
    if value["intent_id"] is not None:
        _identity(value["intent_id"], "intent id")
    _timestamp_string(value["at"], "reconciliation adjustment time")
    _version(value["committed_version"], "adjustment committed version")
    _decimal_string(value["settled_cash_usd"], "adjusted settled cash")
    if type(value["position_quantity"]) is not int or value["position_quantity"] < 0:
        raise ValueError("Invalid adjusted position quantity")
    _mark(value["mark"])
    if not isinstance(value["halt_reasons"], list) or value["halt_reasons"] != sorted(set(value["halt_reasons"])):
        raise ValueError("Invalid adjusted halt reasons")
    for field in ("reserved_cash_usd", "reserved_exposure_gbp", "reserved_loss_gbp"):
        _decimal_string(value[field], field.replace("_", " "))
    return value


def _read_state(connection):
    row = connection.execute("SELECT payload FROM account_state WHERE id=1").fetchone()
    if row is None:
        raise ValueError("Order account state missing; explicit recovery required")
    state = _parse_state(row[0])
    records = []
    for intent_id, candidate_id, client_order_id, proposal_sha, raw in connection.execute(
            "SELECT intent_id,candidate_id,client_order_id,proposal_sha256,payload FROM intents ORDER BY committed_version"):
        record = _record_payload(raw)
        if (intent_id, candidate_id, client_order_id, proposal_sha) != (
                record["intent_id"], record["candidate_id"], record["client_order_id"], record["proposal_sha256"]):
            raise ValueError("Intent identity columns disagree with payload")
        records.append(record)
    incidents = []
    for incident_id, raw in connection.execute("SELECT incident_id,payload FROM incidents ORDER BY committed_version"):
        incident = decode(raw)
        if (not isinstance(incident, dict) or set(incident) != {
                "incident_id", "kind", "incoming", "matches", "committed_version"}
                or incident_id != incident["incident_id"] or incident["kind"] != "identity_conflict"
                or not isinstance(incident["matches"], list)):
            raise ValueError("Invalid stored order incident")
        _version(incident["committed_version"], "incident committed version")
        incoming = incident["incoming"]
        if (not isinstance(incoming, dict) or set(incoming) != {
                "intent_id", "candidate_id", "client_order_id", "proposal_sha256"}
                or incident["matches"] != sorted(set(incident["matches"]))
                or not set(incident["matches"]) <= {record["intent_id"] for record in records}):
            raise ValueError("Invalid stored order incident identities")
        for field in ("intent_id", "candidate_id", "client_order_id"):
            _identity(incoming[field], "incident " + field.replace("_", " "))
        if not isinstance(incoming["proposal_sha256"], str) or not re.fullmatch(r"[0-9a-f]{64}", incoming["proposal_sha256"]):
            raise ValueError("Invalid incident proposal digest")
        identity = {"kind": incident["kind"], "incoming": incident["incoming"],
                    "matches": incident["matches"]}
        if incident_id != digest(identity):
            raise ValueError("Stored order incident digest mismatch")
        incidents.append(incident)
    releases = []
    release_rows = [] if connection.execute("PRAGMA user_version").fetchone()[0] < 2 else connection.execute(
        "SELECT intent_id,payload FROM reservation_releases ORDER BY committed_version")
    for intent_id, raw in release_rows:
        release = _release_payload(raw)
        if intent_id != release["intent_id"]:
            raise ValueError("Reservation release identity columns disagree with payload")
        record = next((row for row in records if row["intent_id"] == intent_id), None)
        if record is None or record["state"] != "reserved":
            raise ValueError("Reservation release has no accepted admission")
        if utc(release["at"]) < utc(record["reservation"]["expires_at"]):
            raise ValueError("Reservation was released before its authority expired")
        releases.append(release)
    adjustments = []
    adjustment_rows = [] if connection.execute("PRAGMA user_version").fetchone()[0] < 3 else connection.execute(
        "SELECT reconciliation_id,payload FROM reconciliation_adjustments ORDER BY committed_version")
    for reconciliation_id, raw in adjustment_rows:
        adjustment = _adjustment_payload(raw)
        if reconciliation_id != adjustment["reconciliation_id"]:
            raise ValueError("Reconciliation adjustment identity columns disagree with payload")
        if adjustment["intent_id"] is not None and not any(
                row["intent_id"] == adjustment["intent_id"] and row["state"] == "reserved"
                for row in records):
            raise ValueError("Reconciliation adjustment has no admitted intent")
        adjustments.append(adjustment)
    events = []
    for expected, (sequence, kind, key, payload_sha) in enumerate(connection.execute(
            "SELECT sequence,kind,event_key,payload_sha256 FROM audit ORDER BY sequence"), 1):
        if sequence != expected or kind not in ("admission", "incident", "release", "reconciliation"):
            raise ValueError("Order audit sequence or kind mismatch")
        events.append((kind, key, payload_sha))
    expected_events = (
        [(row["committed_version"], "admission", row["intent_id"], digest(row)) for row in records]
        + [(row["committed_version"], "incident", row["incident_id"], digest(row)) for row in incidents]
        + [(row["committed_version"], "release", row["intent_id"], digest(row)) for row in releases]
        + [(row["committed_version"], "reconciliation", row["reconciliation_id"], digest(row))
           for row in adjustments]
    )
    expected_events = [(kind, key, payload_sha) for _, kind, key, payload_sha in sorted(expected_events)]
    if events != expected_events or state["version"] != len(events):
        raise ValueError("Order audit/state reconstruction mismatch")
    if any(row["committed_version"] != index for index, row in enumerate(
            sorted(records + incidents + releases + adjustments,
                   key=lambda item: item["committed_version"]), 1)):
        raise ValueError("Order committed versions are not contiguous")
    attempts = sum(row["attempt_consumed"] for row in records)
    totals = {key: D("0") for key in (
        "reserved_cash_usd", "reserved_exposure_gbp", "reserved_loss_gbp")}
    reservation_owner = None
    for item in sorted(records + releases + adjustments,
                       key=lambda row: row["committed_version"]):
        if "state" in item and item["state"] == "reserved":
            if totals["reserved_cash_usd"] != 0:
                raise ValueError("Multiple entry reservations violate the account slot")
            totals = {
                "reserved_cash_usd": money(item["reservation"]["cash_usd"]),
                "reserved_exposure_gbp": money(item["reservation"]["exposure_gbp"]),
                "reserved_loss_gbp": money(item["reservation"]["planned_loss_gbp"]),
            }
            reservation_owner = item["intent_id"]
        elif "reason" in item and item.get("reason") == "expired_authority":
            totals = {key: D("0") for key in totals}
        elif "reconciliation_id" in item:
            if (item["intent_id"] is None or item["intent_id"] != reservation_owner) and any(
                    money(item[key]) != value for key, value in totals.items()):
                raise ValueError("Reconciliation changed another intent's reservation")
            totals = {key: money(item[key]) for key in totals}
    if attempts != state["attempts"] or any(money(state[key]) != value for key, value in totals.items()):
        raise ValueError("Order reservations or attempts disagree with audit")
    if adjustments:
        latest = adjustments[-1]
        for key in ("settled_cash_usd", "position_quantity", "mark", "halt_reasons"):
            if state[key] != latest[key]:
                raise ValueError("Order account projection disagrees with reconciliation")
    expected_unresolved = ["identity_conflict"] if incidents else []
    if state["unresolved_reasons"] != expected_unresolved:
        raise ValueError("Order incidents disagree with account block")
    if connection.execute("PRAGMA user_version").fetchone()[0] == REDUCING_DATABASE_VERSION:
        # V4 is one authoritative store: legacy account/writer/reconciliation
        # reads must also fail closed when its allocation journal is damaged.
        from . import order_allocations
        order_allocations._read(connection)
    return state


def _allocation_blocks(connection):
    if connection.execute("PRAGMA user_version").fetchone()[0] != REDUCING_DATABASE_VERSION:
        return []
    from . import order_allocations
    allocation, _, _ = order_allocations._read(connection)
    return allocation["unresolved_reasons"]


def _require_allocation_clear(connection):
    if _allocation_blocks(connection):
        raise ValueError("Reducing allocation state is unresolved")


def _report(state, reconciliation=None, allocation_blocks=()):
    assessment = assess(_mark(state["mark"]), _mark(state["session_start"]),
                        _mark(state["week_start"]), tuple(state["halt_reasons"]))
    blocked = list(state["halt_reasons"] + state["unresolved_reasons"]) + list(allocation_blocks)
    if reconciliation is not None and reconciliation["status"] != "reconciled":
        blocked.extend(reconciliation["unresolved_reasons"] or ["reconciliation_required"])
    if state["attempts"] >= MAX_ATTEMPTS:
        blocked.append("entry_attempt_limit")
    if money(state["reserved_cash_usd"]) > 0:
        blocked.append("entry_slot_unavailable")
    if state["position_quantity"] != 0:
        blocked.append("position_already_open")
    blocked = sorted(set(blocked))
    available_cash = money(state["settled_cash_usd"]) - money(state["reserved_cash_usd"])
    return {
        "schema": STATE_SCHEMA, "mode": MODE, "account_id": state["account_id"],
        "environment": state["environment"], "version": state["version"],
        "as_of": state["at"], "session": state["session"], "week": state["week"],
        "versions": {name: state[f"{name}_version"] for name in ("ledger", "risk", "evidence")},
        "policy_sha256": digest(state["policy"]), "calendar_id": state["calendar_id"],
        "attempts": state["attempts"], "attempt_limit": MAX_ATTEMPTS,
        "position_quantity": state["position_quantity"],
        "settled_cash_usd": state["settled_cash_usd"],
        "reserved_cash_usd": state["reserved_cash_usd"],
        "available_settled_cash_usd": str(available_cash),
        "reserved_exposure_gbp": state["reserved_exposure_gbp"],
        "reserved_loss_gbp": state["reserved_loss_gbp"],
        "assessment": asdict(assessment), "blocked": bool(blocked),
        "blocked_reasons": blocked, "live_trading_enabled": False,
    }


def _initialize(path, snapshot, database_version):
    if database_version not in (DATABASE_VERSION, REDUCING_DATABASE_VERSION):
        raise ValueError("Unsupported new order database version")
    if not isinstance(snapshot, dict) or set(snapshot) != SNAPSHOT_FIELDS or snapshot["schema"] != ACCOUNT_SCHEMA:
        raise ValueError("Synthetic account snapshot fields do not match the contract")
    account_id = _identity(snapshot["account_id"], "account id")
    if snapshot["environment"] != "synthetic":
        raise ValueError("Only the synthetic environment is supported")
    at = _timestamp_string(snapshot["at"], "snapshot time")
    session, week = _periods(at.isoformat())
    if session_bounds(session) is None:
        raise ValueError("Synthetic order account must start on a supported trading session")
    settled = _decimal_string(snapshot["settled_cash_usd"], "settled cash")
    if type(snapshot["position_quantity"]) is not int or snapshot["position_quantity"] != 0:
        raise ValueError("P4.2 initial synthetic account must be flat")
    mark, session_start, week_start = map(
        _mark, (snapshot["mark"], snapshot["session_start"], snapshot["week_start"])
    )
    if not isinstance(snapshot["halt_reasons"], list) or snapshot["halt_reasons"] != sorted(set(snapshot["halt_reasons"])):
        raise ValueError("Initial halt reasons must be a sorted unique list")
    assessment = assess(mark, session_start, week_start, tuple(snapshot["halt_reasons"]))
    if list(assessment.halt_reasons) != snapshot["halt_reasons"]:
        raise ValueError("Initial halt reasons omit a triggered loss limit")
    for field in ("ledger_version", "risk_version", "evidence_version"):
        _version(snapshot[field], field.replace("_", " "))
    state = {
        "schema": STATE_SCHEMA, "version": 0, "policy": _policy_payload(),
        "calendar_id": CALENDAR_ID, "account_id": account_id, "environment": "synthetic",
        "at": at.isoformat(), "session": session, "week": week,
        "settled_cash_usd": str(settled), "position_quantity": 0,
        "mark": _mark_payload(mark), "session_start": _mark_payload(session_start),
        "week_start": _mark_payload(week_start),
        "ledger_version": snapshot["ledger_version"], "risk_version": snapshot["risk_version"],
        "evidence_version": snapshot["evidence_version"],
        "halt_reasons": list(assessment.halt_reasons), "attempts": 0,
        "reserved_cash_usd": "0", "reserved_exposure_gbp": "0", "reserved_loss_gbp": "0",
        "unresolved_reasons": [], "live_trading_enabled": False,
    }
    path = Path(path)
    descriptor = os.open(path, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
    os.close(descriptor)
    try:
        connection = sqlite3.connect(path)
        connection.execute("PRAGMA synchronous=FULL")
        connection.execute(f"PRAGMA application_id={APP_ID}")
        connection.execute(f"PRAGMA user_version={database_version}")
        connection.execute("CREATE TABLE account_state (id INTEGER PRIMARY KEY CHECK(id=1), payload TEXT NOT NULL)")
        connection.execute("CREATE TABLE intents (intent_id TEXT PRIMARY KEY, candidate_id TEXT UNIQUE NOT NULL, client_order_id TEXT UNIQUE NOT NULL, proposal_sha256 TEXT NOT NULL, committed_version INTEGER UNIQUE NOT NULL, payload TEXT NOT NULL)")
        connection.execute("CREATE TABLE incidents (incident_id TEXT PRIMARY KEY, committed_version INTEGER UNIQUE NOT NULL, payload TEXT NOT NULL)")
        connection.execute("CREATE TABLE reservation_releases (intent_id TEXT PRIMARY KEY, committed_version INTEGER UNIQUE NOT NULL, payload TEXT NOT NULL)")
        connection.execute("CREATE TABLE audit (sequence INTEGER PRIMARY KEY, kind TEXT NOT NULL, event_key TEXT NOT NULL, payload_sha256 TEXT NOT NULL)")
        connection.execute("CREATE TABLE writer_state (id INTEGER PRIMARY KEY CHECK(id=1), payload TEXT NOT NULL)")
        connection.execute("CREATE TABLE submissions (operation_id TEXT PRIMARY KEY, intent_id TEXT UNIQUE NOT NULL, client_order_id TEXT UNIQUE NOT NULL, broker_order_id TEXT UNIQUE, payload TEXT NOT NULL)")
        connection.execute("CREATE TABLE writer_events (sequence INTEGER PRIMARY KEY, event_id TEXT UNIQUE NOT NULL, kind TEXT NOT NULL, payload_sha256 TEXT NOT NULL, payload TEXT NOT NULL)")
        connection.execute("CREATE TABLE reconciliation_state (id INTEGER PRIMARY KEY CHECK(id=1), payload TEXT NOT NULL)")
        connection.execute("CREATE TABLE reconciliation_inbox (snapshot_id TEXT PRIMARY KEY, payload_sha256 TEXT NOT NULL, payload TEXT NOT NULL)")
        connection.execute("CREATE TABLE reconciliation_events (sequence INTEGER PRIMARY KEY, event_id TEXT UNIQUE NOT NULL, kind TEXT NOT NULL, payload_sha256 TEXT NOT NULL, payload TEXT NOT NULL)")
        connection.execute("CREATE TABLE reconciliation_adjustments (reconciliation_id TEXT PRIMARY KEY, committed_version INTEGER UNIQUE NOT NULL, payload TEXT NOT NULL)")
        writer = {"schema": "order-writer-state-v1", "version": 0, "epoch": 0,
                  "owner_id": None, "claim_id": None, "claimed_at": None,
                  "disarmed": True, "unresolved_reasons": [],
                  "live_trading_enabled": False}
        connection.execute("INSERT INTO account_state VALUES (1, ?)", (pack(state),))
        connection.execute("INSERT INTO writer_state VALUES (1, ?)", (pack(writer),))
        reconciliation = {
            "schema": "order-reconciliation-state-v1", "version": 0,
            "account_id": account_id, "environment": "synthetic",
            "baseline_settled_cash_usd": str(settled), "as_of": at.isoformat(),
            "status": "reconciled", "last_snapshot_id": None,
            "unresolved_reasons": [], "executions": [], "commissions": [],
            "order_projection": None,
            "live_trading_enabled": False,
        }
        connection.execute("INSERT INTO reconciliation_state VALUES (1, ?)", (pack(reconciliation),))
        if database_version == REDUCING_DATABASE_VERSION:
            from . import order_allocations
            order_allocations._initialize_tables(connection, account_id, at)
        connection.commit()
        connection.close()
    except BaseException:
        if "connection" in locals():
            connection.close()
        path.unlink(missing_ok=True)
        raise
    return _report(state)


def initialize(path, snapshot):
    """Create the established v3 entry/reconciliation store."""
    return _initialize(path, snapshot, DATABASE_VERSION)


def status(path):
    with database(path) as connection:
        state = _read_state(connection)
        reconciliation = None
        if connection.execute("PRAGMA user_version").fetchone()[0] >= 3:
            from . import order_reconciliation
            reconciliation, _ = order_reconciliation._read(connection)
        return _report(state, reconciliation, _allocation_blocks(connection))


def history(path):
    with database(path) as connection:
        _read_state(connection)
        output = []
        for kind, key in connection.execute("SELECT kind,event_key FROM audit ORDER BY sequence"):
            if kind == "admission":
                table, column = "intents", "intent_id"
            elif kind == "incident":
                table, column = "incidents", "incident_id"
            elif kind == "release":
                table, column = "reservation_releases", "intent_id"
            else:
                table, column = "reconciliation_adjustments", "reconciliation_id"
            raw = connection.execute(f"SELECT payload FROM {table} WHERE {column}=?", (key,)).fetchone()[0]
            output.append(decode(raw))
        return output


def _shallow_proposal(proposal):
    if not isinstance(proposal, dict):
        raise ValueError("Order proposal must be an object")
    return tuple(_identity(proposal.get(field), field.replace("_", " "))
                 for field in ("intent_id", "candidate_id", "client_order_id"))


def _validated_proposal(proposal, state):
    if set(proposal) != PROPOSAL_FIELDS or proposal["schema"] != ADMISSION_SCHEMA:
        raise ValueError("Order proposal fields do not match the admission contract")
    if proposal["account_id"] != state["account_id"] or proposal["environment"] != "synthetic":
        raise ValueError("Order proposal account or environment mismatch")
    for field in ("expected_account_version", "expected_ledger_version", "expected_risk_version", "expected_evidence_version"):
        _version(proposal[field], field.replace("_", " "))
    if proposal["expected_account_version"] != state["version"]:
        raise ValueError("Account version changed; read status before retrying")
    for field in ("ledger", "risk", "evidence"):
        if proposal[f"expected_{field}_version"] != state[f"{field}_version"]:
            raise ValueError(f"{field.capitalize()} version changed; refresh bound evidence")
    if proposal["expected_policy_sha256"] != digest(state["policy"]):
        raise ValueError("Risk policy digest changed; refresh bound authority")
    _identity(proposal["instrument_id"], "instrument id")
    symbol = proposal["symbol"]
    if not isinstance(symbol, str) or not re.fullmatch(r"[A-Z][A-Z0-9]{0,9}", symbol):
        raise ValueError("Invalid stock symbol")
    if (proposal["currency"], proposal["side"], proposal["purpose"],
            proposal["order_type"], proposal["time_in_force"]) != ("USD", "buy", "entry", "limit", "day"):
        raise ValueError("P4.2 supports synthetic USD long-entry day-limit orders only")
    quantity = shares(proposal["quantity"])
    entry = _decimal_string(proposal["limit_price_usd"], "limit price", allow_zero=False)
    stop = _decimal_string(proposal["stop_price_usd"], "stop price", allow_zero=False)
    fx = _decimal_string(proposal["usd_to_gbp"], "USD to GBP rate", allow_zero=False)
    entry_fee = _decimal_string(proposal["entry_fee_usd"], "entry fee")
    exit_fee = _decimal_string(proposal["exit_fee_usd"], "exit fee")
    slip = _decimal_string(proposal["slippage_usd_per_share"], "slippage allowance")
    effective_entry, effective_stop = entry + slip, stop - slip
    if effective_stop <= 0 or stop >= entry:
        raise ValueError("Long stop and slippage allowance are invalid")
    decision = _timestamp_string(proposal["decision_at"], "decision time")
    expires = _timestamp_string(proposal["expires_at"], "expiry")
    quote = _timestamp_string(proposal["quote_at"], "quote time")
    fx_at = _timestamp_string(proposal["fx_at"], "FX time")
    if not decision < expires <= decision + MAX_FRESHNESS:
        raise ValueError("Admission expiry must be after the decision and within 60 seconds")
    reservation = {
        "cash_usd": str(quantity * effective_entry + entry_fee + exit_fee),
        "exposure_gbp": str(quantity * effective_entry * fx),
        "planned_loss_gbp": str(planned_long_loss(
            quantity, effective_entry, effective_stop, fx, (entry_fee + exit_fee) * fx
        )),
        "expires_at": expires.isoformat(),
    }
    return decision, quote, fx_at, reservation


def _current_result(record, state, duplicate=False, reconciliation=None):
    return {
        "schema": ADMISSION_SCHEMA, "mode": MODE, "outcome": record["state"],
        "intent_id": record["intent_id"], "candidate_id": record["candidate_id"],
        "client_order_id": record["client_order_id"], "proposal_sha256": record["proposal_sha256"],
        "attempt_consumed": record["attempt_consumed"], "reasons": record["reasons"],
        "reservation": record["reservation"], "committed_version": record["committed_version"],
        "duplicate": duplicate, "account": _report(state, reconciliation),
        "live_trading_enabled": False,
    }


def _write_state(connection, state):
    connection.execute("UPDATE account_state SET payload=? WHERE id=1", (pack(state),))


def _release_reservation(connection, state, record, at):
    """Release never-dispatched authority only after its immutable expiry."""
    at = _timestamp_string(at, "release time")
    if record["state"] != "reserved" or at < utc(record["reservation"]["expires_at"]):
        raise ValueError("Reservation authority has not expired")
    existing = connection.execute(
        "SELECT payload FROM reservation_releases WHERE intent_id=?", (record["intent_id"],)
    ).fetchone()
    if existing is not None:
        return _release_payload(existing[0])
    if money(state["reserved_cash_usd"]) == 0:
        raise ValueError("Reservation resources are already unavailable")
    version = state["version"] + 1
    release = {"intent_id": record["intent_id"], "reason": "expired_authority",
               "at": at.isoformat(), "committed_version": version}
    connection.execute("INSERT INTO reservation_releases VALUES (?, ?, ?)",
                       (record["intent_id"], version, pack(release)))
    connection.execute("INSERT INTO audit VALUES (?, 'release', ?, ?)",
                       (version, record["intent_id"], digest(release)))
    state["version"] = version
    state["reserved_cash_usd"] = "0"
    state["reserved_exposure_gbp"] = "0"
    state["reserved_loss_gbp"] = "0"
    _write_state(connection, state)
    return release


def admit(path, proposal):
    intent_id, candidate_id, client_order_id = _shallow_proposal(proposal)
    proposal_sha = digest(proposal)
    with database(path, write=True) as connection:
        state = _read_state(connection)
        reconciliation = None
        if connection.execute("PRAGMA user_version").fetchone()[0] >= 3:
            from . import order_reconciliation
            reconciliation, _ = order_reconciliation._read(connection)
        rows = connection.execute(
            "SELECT payload FROM intents WHERE intent_id=? OR candidate_id=? OR client_order_id=?",
            (intent_id, candidate_id, client_order_id),
        ).fetchall()
        records = [_record_payload(row[0]) for row in rows]
        if len(records) == 1 and all(records[0][field] == value for field, value in (
                ("intent_id", intent_id), ("candidate_id", candidate_id),
                ("client_order_id", client_order_id), ("proposal_sha256", proposal_sha))):
            release = None
            if connection.execute("PRAGMA user_version").fetchone()[0] >= 2:
                release = connection.execute(
                    "SELECT payload FROM reservation_releases WHERE intent_id=?", (intent_id,)
                ).fetchone()
            if release is not None:
                released = _release_payload(release[0])
                result = _current_result(records[0], state, duplicate=True,
                                         reconciliation=reconciliation)
                result.update(outcome="cancelled", reasons=[released["reason"]],
                              reservation=None, release=released)
                return result
            return _current_result(records[0], state, duplicate=True,
                                   reconciliation=reconciliation)
        _require_allocation_clear(connection)
        if connection.execute("PRAGMA user_version").fetchone()[0] == REDUCING_DATABASE_VERSION:
            if connection.execute(
                    "SELECT 1 FROM reducing_allocations WHERE allocation_id=? OR client_order_id=?",
                    (intent_id, client_order_id)).fetchone():
                raise ValueError("Entry identities collide with a reducing allocation")
        if records:
            incoming = {"intent_id": intent_id, "candidate_id": candidate_id,
                        "client_order_id": client_order_id, "proposal_sha256": proposal_sha}
            matches = sorted(row["intent_id"] for row in records)
            incident_id = digest({"kind": "identity_conflict", "incoming": incoming, "matches": matches})
            existing = connection.execute("SELECT payload FROM incidents WHERE incident_id=?", (incident_id,)).fetchone()
            if existing is None:
                version = state["version"] + 1
                incident = {"incident_id": incident_id, "kind": "identity_conflict",
                            "incoming": incoming, "matches": matches, "committed_version": version}
                connection.execute("INSERT INTO incidents VALUES (?, ?, ?)",
                                   (incident_id, version, pack(incident)))
                connection.execute("INSERT INTO audit VALUES (?, 'incident', ?, ?)",
                                   (version, incident_id, digest(incident)))
                state["version"] = version
                state["unresolved_reasons"] = ["identity_conflict"]
                _write_state(connection, state)
            return {"schema": ADMISSION_SCHEMA, "mode": MODE, "outcome": "identity_conflict",
                    "intent_id": intent_id, "reasons": ["identity_conflict"],
                    "duplicate": existing is not None,
                    "account": _report(state, reconciliation),
                    "live_trading_enabled": False}
        decision, quote, fx_at, reservation = _validated_proposal(proposal, state)
        reasons = list(_report(state, reconciliation)["blocked_reasons"])
        for label, observed in (("account", utc(state["at"])), ("quote", quote), ("fx", fx_at)):
            age = decision - observed
            if not timedelta(0) <= age <= MAX_FRESHNESS:
                reasons.append(label + "_stale_or_future")
        local = decision.astimezone(ZoneInfo("America/New_York"))
        if local.date().isoformat() != state["session"]:
            reasons.append("period_review_required")
        if session_bounds(local.date().isoformat()) is None or not time(10) <= local.time() < time(11, 30):
            reasons.append("outside_entry_window")
        cash = money(reservation["cash_usd"])
        exposure = money(reservation["exposure_gbp"])
        loss = money(reservation["planned_loss_gbp"])
        if cash > money(state["settled_cash_usd"]) - money(state["reserved_cash_usd"]):
            reasons.append("insufficient_settled_cash")
        if exposure + money(state["reserved_exposure_gbp"]) > MAX_EXPOSURE_GBP:
            reasons.append("exposure_limit")
        if loss > Policy().trade_loss:
            reasons.append("trade_loss_limit")
        assessment = assess(_mark(state["mark"]), _mark(state["session_start"]),
                            _mark(state["week_start"]), tuple(state["halt_reasons"]))
        for name, pnl, limit in (
                ("overall", assessment.cumulative_pnl, Policy().overall_loss),
                ("daily", assessment.daily_pnl, Policy().daily_loss),
                ("weekly", assessment.weekly_pnl, Policy().weekly_loss)):
            if loss + money(state["reserved_loss_gbp"]) > limit + pnl:
                reasons.append(name + "_loss_headroom")
        reasons = sorted(set(reasons))
        consume_attempt = state["attempts"] < MAX_ATTEMPTS
        if consume_attempt:
            state["attempts"] += 1
        accepted = not reasons
        if accepted:
            state["reserved_cash_usd"] = reservation["cash_usd"]
            state["reserved_exposure_gbp"] = reservation["exposure_gbp"]
            state["reserved_loss_gbp"] = reservation["planned_loss_gbp"]
        version = state["version"] + 1
        state["version"] = version
        record = {
            "intent_id": intent_id, "candidate_id": candidate_id,
            "client_order_id": client_order_id, "proposal_sha256": proposal_sha,
            "proposal": proposal, "state": "reserved" if accepted else "rejected",
            "attempt_consumed": consume_attempt, "reasons": reasons,
            "reservation": reservation if accepted else None, "committed_version": version,
        }
        connection.execute("INSERT INTO intents VALUES (?, ?, ?, ?, ?, ?)",
                           (intent_id, candidate_id, client_order_id, proposal_sha,
                            version, pack(record)))
        connection.execute("INSERT INTO audit VALUES (?, 'admission', ?, ?)",
                           (version, intent_id, digest(record)))
        _write_state(connection, state)
        return _current_result(record, state, reconciliation=reconciliation)
