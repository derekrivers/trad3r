"""Atomic v4 synthetic reducing-order allocations; no dispatch capability."""
from copy import deepcopy
from decimal import Decimal as D

from .ledger import utc
from .risk import money
from . import order_reconciliation, order_store as store, order_writer


REQUEST_SCHEMA = "reducing-allocation-request-v1"
STATE_SCHEMA = "reducing-allocation-state-v1"
REPORT_SCHEMA = "reducing-allocation-report-v1"
MODE = "synthetic_reducing_allocation_only"
PURPOSES = {"protective_stop", "reducing_exit"}
REQUEST_FIELDS = {
    "schema", "allocation_id", "client_order_id", "account_id", "environment",
    "entry_intent_id", "instrument_id", "purpose", "quantity", "fee_bound_usd",
    "decision_at", "expires_at", "owner_id", "writer_epoch",
    "expected_account_version", "expected_reconciliation_version",
    "expected_writer_version", "expected_allocation_version", "expected_policy_sha256",
}


def _initialize_tables(connection, account_id, at):
    state = {
        "schema": STATE_SCHEMA, "version": 0, "account_id": account_id,
        "environment": "synthetic", "as_of": at.isoformat(), "entry_intent_id": None,
        "instrument_id": None, "verified_quantity": 0, "exit_fee_allowance_usd": "0",
        "reserved_quantity": 0, "reserved_fee_usd": "0",
        "unresolved_reasons": [], "live_trading_enabled": False,
    }
    connection.execute(
        "CREATE TABLE reducing_allocation_state "
        "(id INTEGER PRIMARY KEY CHECK(id=1), payload TEXT NOT NULL)")
    connection.execute(
        "CREATE TABLE reducing_allocations "
        "(allocation_id TEXT PRIMARY KEY, client_order_id TEXT UNIQUE NOT NULL, "
        "request_sha256 TEXT NOT NULL, committed_version INTEGER UNIQUE NOT NULL, "
        "payload TEXT NOT NULL)")
    connection.execute(
        "CREATE TABLE reducing_allocation_incidents "
        "(incident_id TEXT PRIMARY KEY, committed_version INTEGER UNIQUE NOT NULL, "
        "payload TEXT NOT NULL)")
    connection.execute(
        "CREATE TABLE reducing_allocation_audit "
        "(sequence INTEGER PRIMARY KEY, kind TEXT NOT NULL, event_key TEXT NOT NULL, "
        "payload_sha256 TEXT NOT NULL)")
    connection.execute("INSERT INTO reducing_allocation_state VALUES (1, ?)",
                       (store.pack(state),))


def initialize(path, snapshot):
    """Create a fresh v4 store. Existing databases are never upgraded in place."""
    return store._initialize(path, snapshot, store.REDUCING_DATABASE_VERSION)


def _state_payload(raw):
    value = store.decode(raw)
    required = {
        "schema", "version", "account_id", "environment", "as_of",
        "entry_intent_id", "instrument_id", "verified_quantity",
        "exit_fee_allowance_usd", "reserved_quantity", "reserved_fee_usd",
        "unresolved_reasons", "live_trading_enabled",
    }
    if (not isinstance(value, dict) or set(value) != required
            or value["schema"] != STATE_SCHEMA or value["environment"] != "synthetic"
            or value["live_trading_enabled"] is not False):
        raise ValueError("Invalid reducing allocation state")
    store._identity(value["account_id"], "allocation account id")
    store._version(value["version"], "allocation version")
    store._timestamp_string(value["as_of"], "allocation state time")
    for field in ("entry_intent_id", "instrument_id"):
        if value[field] is not None:
            store._identity(value[field], field.replace("_", " "))
    for field in ("verified_quantity", "reserved_quantity"):
        if type(value[field]) is not int or value[field] < 0:
            raise ValueError("Invalid reducing allocation quantity")
    for field in ("exit_fee_allowance_usd", "reserved_fee_usd"):
        store._decimal_string(value[field], field.replace("_", " "))
    if (value["reserved_quantity"] > value["verified_quantity"]
            or money(value["reserved_fee_usd"]) > money(value["exit_fee_allowance_usd"])):
        raise ValueError("Reducing allocations exceed the stored capacity")
    if (not isinstance(value["unresolved_reasons"], list)
            or value["unresolved_reasons"] != sorted(set(value["unresolved_reasons"]))):
        raise ValueError("Invalid reducing allocation reasons")
    return value


def _record_payload(raw):
    value = store.decode(raw)
    required = {
        "allocation_id", "client_order_id", "request_sha256", "request", "state",
        "reasons", "quantity", "fee_bound_usd", "verified_quantity",
        "exit_fee_allowance_usd", "committed_version",
    }
    if not isinstance(value, dict) or set(value) != required:
        raise ValueError("Invalid reducing allocation record")
    for field in ("allocation_id", "client_order_id"):
        store._identity(value[field], field.replace("_", " "))
    if value["request_sha256"] != store.digest(value["request"]):
        raise ValueError("Reducing allocation request digest mismatch")
    _validated_request(value["request"])
    if any(value[field] != value["request"][field]
           for field in ("allocation_id", "client_order_id", "quantity")):
        raise ValueError("Reducing allocation record disagrees with its request")
    if money(value["fee_bound_usd"]) != money(value["request"]["fee_bound_usd"]):
        raise ValueError("Reducing allocation fee disagrees with its request")
    if value["state"] not in ("reserved", "rejected"):
        raise ValueError("Invalid reducing allocation outcome")
    if (not isinstance(value["reasons"], list)
            or value["reasons"] != sorted(set(value["reasons"]))):
        raise ValueError("Invalid reducing allocation reasons")
    for field in ("quantity", "verified_quantity"):
        if type(value[field]) is not int or value[field] <= 0:
            raise ValueError("Invalid reducing allocation record quantity")
    for field in ("fee_bound_usd", "exit_fee_allowance_usd"):
        store._decimal_string(value[field], field.replace("_", " "))
    store._version(value["committed_version"], "allocation committed version")
    if value["state"] == "reserved" and value["reasons"]:
        raise ValueError("Reserved reducing allocation has rejection reasons")
    if value["state"] == "rejected" and not value["reasons"]:
        raise ValueError("Rejected reducing allocation has no reason")
    return value


def _incident_payload(raw):
    value = store.decode(raw)
    required = {"incident_id", "kind", "at", "incoming", "matches", "committed_version"}
    if (not isinstance(value, dict) or set(value) != required
            or value["kind"] != "allocation_identity_conflict"):
        raise ValueError("Invalid reducing allocation incident")
    store._identity(value["incident_id"], "allocation incident id")
    store._timestamp_string(value["at"], "allocation incident time")
    store._version(value["committed_version"], "allocation incident version")
    if (not isinstance(value["incoming"], dict)
            or set(value["incoming"]) != {"allocation_id", "client_order_id", "request_sha256"}
            or not isinstance(value["matches"], list)
            or value["matches"] != sorted(set(value["matches"]))):
        raise ValueError("Invalid reducing allocation incident identities")
    for field in ("allocation_id", "client_order_id"):
        store._identity(value["incoming"][field], "incoming " + field.replace("_", " "))
    if (not isinstance(value["incoming"]["request_sha256"], str)
            or len(value["incoming"]["request_sha256"]) != 64
            or any(character not in "0123456789abcdef"
                   for character in value["incoming"]["request_sha256"])):
        raise ValueError("Invalid reducing allocation incident digest")
    identity = {"kind": value["kind"], "incoming": value["incoming"],
                "matches": value["matches"]}
    if value["incident_id"] != "alloc-conflict-" + store.digest(identity)[:32]:
        raise ValueError("Reducing allocation incident digest mismatch")
    return value


def _read(connection):
    if connection.execute("PRAGMA user_version").fetchone()[0] != store.REDUCING_DATABASE_VERSION:
        raise ValueError("Reducing allocations require a fresh v4 order database")
    row = connection.execute("SELECT payload FROM reducing_allocation_state WHERE id=1").fetchone()
    if row is None:
        raise ValueError("Reducing allocation state missing; explicit recovery required")
    state = _state_payload(row[0])
    records = []
    for allocation_id, client_order_id, request_sha, raw in connection.execute(
            "SELECT allocation_id,client_order_id,request_sha256,payload "
            "FROM reducing_allocations ORDER BY committed_version"):
        record = _record_payload(raw)
        if (allocation_id, client_order_id, request_sha) != (
                record["allocation_id"], record["client_order_id"], record["request_sha256"]):
            raise ValueError("Reducing allocation identity columns disagree with payload")
        records.append(record)
    incidents = []
    for incident_id, raw in connection.execute(
            "SELECT incident_id,payload FROM reducing_allocation_incidents ORDER BY committed_version"):
        incident = _incident_payload(raw)
        if incident_id != incident["incident_id"]:
            raise ValueError("Reducing allocation incident identity mismatch")
        if not set(incident["matches"]) <= {record["allocation_id"] for record in records}:
            raise ValueError("Reducing allocation incident references an unknown allocation")
        incidents.append(incident)
    events = []
    for expected, (sequence, kind, key, payload_sha) in enumerate(connection.execute(
            "SELECT sequence,kind,event_key,payload_sha256 "
            "FROM reducing_allocation_audit ORDER BY sequence"), 1):
        if sequence != expected or kind not in ("allocation", "incident"):
            raise ValueError("Reducing allocation audit sequence or kind mismatch")
        events.append((kind, key, payload_sha))
    combined = sorted(records + incidents, key=lambda item: item["committed_version"])
    if any(row["committed_version"] != index for index, row in enumerate(combined, 1)):
        raise ValueError("Reducing allocation versions are not contiguous")
    expected_events = [
        ("allocation" if "allocation_id" in item else "incident",
         item.get("allocation_id", item.get("incident_id")), store.digest(item))
        for item in combined
    ]
    if events != expected_events or state["version"] != len(events):
        raise ValueError("Reducing allocation audit/state reconstruction mismatch")
    reserved_quantity = 0
    reserved_fee = D("0")
    episode = None
    for record in records:
        request = record["request"]
        if request["account_id"] != state["account_id"]:
            raise ValueError("Reducing allocation record account mismatch")
        current_episode = (request["entry_intent_id"], request["instrument_id"],
                           money(record["exit_fee_allowance_usd"]))
        if episode is None:
            episode = current_episode
        elif current_episode != episode:
            raise ValueError("Reducing allocation audit crosses entry episodes")
        reasons = []
        if record["quantity"] > record["verified_quantity"] - reserved_quantity:
            reasons.append("sell_quantity_unavailable")
        if money(record["fee_bound_usd"]) > current_episode[2] - reserved_fee:
            reasons.append("exit_fee_allowance_unavailable")
        reasons = sorted(reasons)
        expected_state = "rejected" if reasons else "reserved"
        if (record["state"], record["reasons"]) != (expected_state, reasons):
            raise ValueError("Reducing allocation outcome disagrees with capacity replay")
        if expected_state == "reserved":
            reserved_quantity += record["quantity"]
            reserved_fee += money(record["fee_bound_usd"])
    latest = records[-1] if records else None
    expected_reasons = ["allocation_identity_conflict"] if incidents else []
    if latest is None:
        expected = (None, None, 0, D("0"))
    else:
        request = latest["request"]
        expected = (request["entry_intent_id"], request["instrument_id"],
                    latest["verified_quantity"], money(latest["exit_fee_allowance_usd"]))
    actual = (state["entry_intent_id"], state["instrument_id"],
              state["verified_quantity"], money(state["exit_fee_allowance_usd"]))
    expected_as_of = (combined[-1]["at"] if "incident_id" in combined[-1]
                      else combined[-1]["request"]["decision_at"]) if combined else state["as_of"]
    if (actual != expected or state["reserved_quantity"] != reserved_quantity
            or money(state["reserved_fee_usd"]) != reserved_fee
            or state["unresolved_reasons"] != expected_reasons
            or utc(state["as_of"]) != utc(expected_as_of)):
        raise ValueError("Reducing allocation projection disagrees with audit replay")
    return state, records, incidents


def _report(state, records):
    available_quantity = state["verified_quantity"] - state["reserved_quantity"]
    available_fee = money(state["exit_fee_allowance_usd"]) - money(state["reserved_fee_usd"])
    return {
        "schema": REPORT_SCHEMA, "mode": MODE, "account_id": state["account_id"],
        "environment": state["environment"], "version": state["version"],
        "as_of": state["as_of"], "entry_intent_id": state["entry_intent_id"],
        "instrument_id": state["instrument_id"],
        "verified_quantity": state["verified_quantity"],
        "reserved_quantity": state["reserved_quantity"],
        "available_quantity": available_quantity,
        "exit_fee_allowance_usd": state["exit_fee_allowance_usd"],
        "reserved_fee_usd": state["reserved_fee_usd"],
        "available_fee_usd": str(available_fee),
        "unresolved_reasons": state["unresolved_reasons"],
        "allocations": deepcopy(records), "live_trading_enabled": False,
    }


def status(path):
    with store.database(path) as connection:
        store._read_state(connection)
        order_reconciliation._read(connection)
        order_writer._read_writer(connection)
        state, records, _ = _read(connection)
        return _report(state, records)


def history(path):
    with store.database(path) as connection:
        store._read_state(connection)
        order_reconciliation._read(connection)
        order_writer._read_writer(connection)
        _, records, incidents = _read(connection)
        return sorted(records + incidents, key=lambda item: item["committed_version"])


def _shallow_request(raw):
    if not isinstance(raw, dict):
        raise ValueError("Reducing allocation request must be an object")
    allocation_id = store._identity(raw.get("allocation_id"), "allocation id")
    client_order_id = store._identity(raw.get("client_order_id"), "client order id")
    at = store._timestamp_string(raw.get("decision_at"), "allocation decision time")
    return allocation_id, client_order_id, at


def _validated_request(raw):
    if set(raw) != REQUEST_FIELDS or raw["schema"] != REQUEST_SCHEMA:
        raise ValueError("Reducing allocation request fields do not match the contract")
    for field in ("account_id", "entry_intent_id", "instrument_id", "owner_id"):
        store._identity(raw[field], field.replace("_", " "))
    if raw["environment"] != "synthetic" or raw["purpose"] not in PURPOSES:
        raise ValueError("Only synthetic protective-stop and reducing-exit allocations are supported")
    if type(raw["quantity"]) is not int or raw["quantity"] <= 0:
        raise ValueError("Reducing allocation quantity must be a positive whole number")
    fee = store._decimal_string(raw["fee_bound_usd"], "reducing allocation fee bound")
    decision = store._timestamp_string(raw["decision_at"], "allocation decision time")
    expires = store._timestamp_string(raw["expires_at"], "allocation expiry")
    if not decision < expires <= decision + store.MAX_FRESHNESS:
        raise ValueError("Reducing allocation expiry must be within 60 seconds")
    for field in ("writer_epoch", "expected_account_version",
                  "expected_reconciliation_version", "expected_writer_version",
                  "expected_allocation_version"):
        store._version(raw[field], field.replace("_", " "))
    return decision, fee


def _write_state(connection, state):
    connection.execute("UPDATE reducing_allocation_state SET payload=? WHERE id=1",
                       (store.pack(state),))


def admit(path, raw):
    allocation_id, client_order_id, shallow_at = _shallow_request(raw)
    request_sha = store.digest(raw)
    with store.database(path, write=True) as connection:
        account = store._read_state(connection)
        reconciliation, _ = order_reconciliation._read(connection)
        writer, _, _ = order_writer._read_writer(connection)
        state, records, _ = _read(connection)
        rows = connection.execute(
            "SELECT payload FROM reducing_allocations "
            "WHERE allocation_id=? OR client_order_id=?",
            (allocation_id, client_order_id)).fetchall()
        matches = [_record_payload(row[0]) for row in rows]
        if len(matches) == 1 and all(matches[0][field] == value for field, value in (
                ("allocation_id", allocation_id), ("client_order_id", client_order_id),
                ("request_sha256", request_sha))):
            result = _report(state, records)
            result.update(outcome=matches[0]["state"], reasons=matches[0]["reasons"],
                          duplicate=True, allocation=matches[0])
            return result
        if matches:
            if shallow_at < utc(state["as_of"]):
                raise ValueError("Reducing allocation incident time cannot move backwards")
            incoming = {"allocation_id": allocation_id, "client_order_id": client_order_id,
                        "request_sha256": request_sha}
            identities = sorted(row["allocation_id"] for row in matches)
            incident_key = {"kind": "allocation_identity_conflict",
                            "incoming": incoming, "matches": identities}
            incident_id = "alloc-conflict-" + store.digest(incident_key)[:32]
            existing = connection.execute(
                "SELECT payload FROM reducing_allocation_incidents WHERE incident_id=?",
                (incident_id,)).fetchone()
            if existing is None:
                version = state["version"] + 1
                incident = dict(incident_key, incident_id=incident_id,
                                at=shallow_at.isoformat(), committed_version=version)
                connection.execute(
                    "INSERT INTO reducing_allocation_incidents VALUES (?, ?, ?)",
                    (incident_id, version, store.pack(incident)))
                connection.execute(
                    "INSERT INTO reducing_allocation_audit VALUES (?, 'incident', ?, ?)",
                    (version, incident_id, store.digest(incident)))
                state.update(version=version, as_of=shallow_at.isoformat(),
                             unresolved_reasons=["allocation_identity_conflict"])
                _write_state(connection, state)
            result = _report(state, records)
            result.update(outcome="identity_conflict", reasons=["allocation_identity_conflict"],
                          duplicate=existing is not None)
            return result

        decision, fee = _validated_request(raw)
        if decision < utc(state["as_of"]):
            raise ValueError("Reducing allocation decision time cannot move backwards")
        if raw["account_id"] != account["account_id"]:
            raise ValueError("Reducing allocation account mismatch")
        if state["account_id"] != account["account_id"]:
            raise ValueError("Reducing allocation state account mismatch")
        if account["version"] != raw["expected_account_version"]:
            raise ValueError("Account version changed; refresh reducing evidence")
        if reconciliation["version"] != raw["expected_reconciliation_version"]:
            raise ValueError("Reconciliation version changed; refresh reducing evidence")
        if writer["version"] != raw["expected_writer_version"]:
            raise ValueError("Writer version changed; refresh reducing authority")
        if state["version"] != raw["expected_allocation_version"]:
            raise ValueError("Allocation version changed; read allocation status before retrying")
        if raw["expected_policy_sha256"] != store.digest(account["policy"]):
            raise ValueError("Risk policy digest changed; refresh reducing authority")
        if state["unresolved_reasons"] or account["unresolved_reasons"]:
            raise ValueError("Account or reducing allocation state is unresolved")
        if reconciliation["status"] != "reconciled":
            raise ValueError("Complete reconciliation is required before reducing allocation")
        if writer["disarmed"] or writer["unresolved_reasons"]:
            raise ValueError("Writer is disarmed or unresolved")
        if (writer["owner_id"], writer["epoch"]) != (raw["owner_id"], raw["writer_epoch"]):
            raise ValueError("Writer ownership or fencing epoch changed")
        if decision < utc(account["at"]) or decision < utc(reconciliation["as_of"]):
            raise ValueError("Reducing allocation predates current account evidence")
        projection = reconciliation["order_projection"]
        if (projection is None or projection["intent_id"] != raw["entry_intent_id"]
                or projection["executed_quantity"] != account["position_quantity"]
                or account["position_quantity"] <= 0):
            raise ValueError("Verified long entry evidence is required for reducing allocation")
        intent_row = connection.execute(
            "SELECT payload FROM intents WHERE intent_id=?", (raw["entry_intent_id"],)).fetchone()
        if intent_row is None:
            raise ValueError("Reducing allocation entry intent is unknown")
        intent = store._record_payload(intent_row[0])
        proposal = intent["proposal"]
        if (intent["state"] != "reserved" or proposal["instrument_id"] != raw["instrument_id"]
                or proposal["side"] != "buy" or proposal["purpose"] != "entry"):
            raise ValueError("Reducing allocation entry identity mismatch")
        allowance = money(proposal["exit_fee_usd"])
        if money(account["reserved_cash_usd"]) < allowance:
            raise ValueError("Entry exit-fee allowance is not reserved in settled cash")
        if state["entry_intent_id"] is not None and (
                state["entry_intent_id"] != raw["entry_intent_id"]
                or state["instrument_id"] != raw["instrument_id"]
                or money(state["exit_fee_allowance_usd"]) != allowance):
            raise ValueError("Reducing allocation entry episode changed")

        available_quantity = account["position_quantity"] - state["reserved_quantity"]
        if available_quantity < 0:
            raise ValueError("Current position is below already reserved reducing quantity")
        available_fee = allowance - money(state["reserved_fee_usd"])
        reasons = []
        if raw["quantity"] > available_quantity:
            reasons.append("sell_quantity_unavailable")
        if fee > available_fee:
            reasons.append("exit_fee_allowance_unavailable")
        reasons = sorted(reasons)
        version = state["version"] + 1
        record = {
            "allocation_id": allocation_id, "client_order_id": client_order_id,
            "request_sha256": request_sha, "request": deepcopy(raw),
            "state": "rejected" if reasons else "reserved", "reasons": reasons,
            "quantity": raw["quantity"], "fee_bound_usd": str(fee),
            "verified_quantity": account["position_quantity"],
            "exit_fee_allowance_usd": str(allowance), "committed_version": version,
        }
        connection.execute(
            "INSERT INTO reducing_allocations VALUES (?, ?, ?, ?, ?)",
            (allocation_id, client_order_id, request_sha, version, store.pack(record)))
        connection.execute(
            "INSERT INTO reducing_allocation_audit VALUES (?, 'allocation', ?, ?)",
            (version, allocation_id, store.digest(record)))
        state.update(
            version=version, as_of=decision.isoformat(),
            entry_intent_id=raw["entry_intent_id"], instrument_id=raw["instrument_id"],
            verified_quantity=account["position_quantity"],
            exit_fee_allowance_usd=str(allowance),
        )
        if not reasons:
            state["reserved_quantity"] += raw["quantity"]
            state["reserved_fee_usd"] = str(money(state["reserved_fee_usd"]) + fee)
        _write_state(connection, state)
        records.append(record)
        result = _report(state, records)
        result.update(outcome=record["state"], reasons=reasons,
                      duplicate=False, allocation=record)
        return result
