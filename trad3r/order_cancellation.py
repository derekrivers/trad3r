"""Fenced synthetic cancellation operations resolved only by cumulative evidence."""
from copy import deepcopy
from dataclasses import dataclass
from datetime import timedelta

from .ledger import utc
from . import order_reconciliation, order_store as store, order_writer


REQUEST_SCHEMA = "order-cancellation-request-v1"
STATE_SCHEMA = "order-cancellation-state-v1"
RECORD_SCHEMA = "order-cancellation-operation-v1"
EVENT_SCHEMA = "order-cancellation-event-v1"
REPORT_SCHEMA = "order-cancellation-report-v1"
MODE = "synthetic_fenced_cancellation_only"
REQUEST_FIELDS = {
    "schema", "operation_id", "account_id", "environment",
    "target_client_order_id", "target_order_id", "owner_id", "writer_epoch",
    "at", "expires_at", "expected_account_version",
    "expected_entry_reconciliation_version", "expected_reducing_reconciliation_version",
    "expected_writer_version", "expected_allocation_version",
    "expected_cancellation_version",
}
RECORD_FIELDS = {
    "schema", "operation_id", "request", "request_sha256", "command",
    "command_sha256", "target_source", "target_side", "state", "adapter_result",
    "marked_at", "resolved_at", "owner_id", "writer_epoch", "last_event_version",
}
EVENT_FIELDS = {
    "schema", "event_id", "kind", "at", "committed_version", "input_sha256",
    "input", "writer_evidence_sha256", "record", "incident", "state",
}
ACTIVE_STATES = {"cancel_pending", "accepted", "unknown"}
TERMINAL_STATES = {"rejected_working", "confirmed_cancelled", "moot_filled"}
CANCELLATION_REASONS = {
    "cancellation_pending", "cancellation_reconciliation_required",
    "cancellation_unknown", "cancellation_identity_conflict",
}
SYNTHETIC_OUTCOMES = {"accepted", "rejected_working", "denied", "accept_then_timeout"}


class CancellationUncertain(RuntimeError):
    """The synthetic adapter accepted a cancellation but lost its response."""


@dataclass
class SyntheticCancellationAdapter:
    calls: int = 0

    def cancel(self, command, outcome):
        self.calls += 1
        if outcome == "accepted":
            return {"outcome": "accepted", "receipt_id": "synthetic-" + store.digest(command)[:24]}
        if outcome == "rejected_working":
            return {"outcome": "rejected_working", "reason": "synthetic_order_still_working"}
        if outcome == "denied":
            return {"outcome": "unknown", "reason": "synthetic_bare_denial"}
        if outcome == "accept_then_timeout":
            raise CancellationUncertain("synthetic cancellation response lost")
        raise ValueError("Unsupported synthetic cancellation outcome")


def _initialize_tables(connection, account_id, at):
    state = {
        "schema": STATE_SCHEMA, "version": 0, "account_id": account_id,
        "environment": "synthetic", "as_of": at.isoformat(),
        "unresolved_reasons": [], "live_trading_enabled": False,
    }
    connection.execute("CREATE TABLE cancellation_state "
                       "(id INTEGER PRIMARY KEY CHECK(id=1), payload TEXT NOT NULL)")
    connection.execute("CREATE TABLE cancellation_operations "
                       "(operation_id TEXT PRIMARY KEY, target_client_order_id TEXT NOT NULL, "
                       "target_order_id TEXT NOT NULL, request_sha256 TEXT NOT NULL, payload TEXT NOT NULL)")
    connection.execute("CREATE INDEX cancellation_target ON cancellation_operations(target_client_order_id,target_order_id)")
    connection.execute("CREATE TABLE cancellation_incidents "
                       "(incident_id TEXT PRIMARY KEY, request_sha256 TEXT NOT NULL, payload TEXT NOT NULL)")
    connection.execute("CREATE TABLE cancellation_events "
                       "(sequence INTEGER PRIMARY KEY, event_id TEXT UNIQUE NOT NULL, kind TEXT NOT NULL, "
                       "input_sha256 TEXT NOT NULL, payload_sha256 TEXT NOT NULL, payload TEXT NOT NULL)")
    connection.execute("INSERT INTO cancellation_state VALUES (1, ?)", (store.pack(state),))


def _request(raw):
    value = deepcopy(raw)
    if not isinstance(value, dict) or set(value) != REQUEST_FIELDS or value["schema"] != REQUEST_SCHEMA:
        raise ValueError("Cancellation request fields do not match the contract")
    for field in ("operation_id", "account_id", "target_client_order_id", "target_order_id", "owner_id"):
        store._identity(value[field], field.replace("_", " "))
    if value["environment"] != "synthetic":
        raise ValueError("Only synthetic cancellation is supported")
    store._timestamp_string(value["at"], "cancellation decision time")
    store._timestamp_string(value["expires_at"], "cancellation expiry")
    for field in ("writer_epoch", "expected_account_version",
                  "expected_entry_reconciliation_version",
                  "expected_reducing_reconciliation_version", "expected_writer_version",
                  "expected_allocation_version", "expected_cancellation_version"):
        store._version(value[field], field.replace("_", " "))
    return value


def _state(raw):
    value = store.decode(raw) if not isinstance(raw, dict) else deepcopy(raw)
    required = {"schema", "version", "account_id", "environment", "as_of",
                "unresolved_reasons", "live_trading_enabled"}
    if (not isinstance(value, dict) or set(value) != required or value["schema"] != STATE_SCHEMA
            or value["environment"] != "synthetic" or value["live_trading_enabled"] is not False):
        raise ValueError("Invalid cancellation state")
    store._version(value["version"], "cancellation version")
    store._identity(value["account_id"], "cancellation account")
    store._timestamp_string(value["as_of"], "cancellation state time")
    if (not isinstance(value["unresolved_reasons"], list)
            or value["unresolved_reasons"] != sorted(set(value["unresolved_reasons"]))
            or not set(value["unresolved_reasons"]) <= CANCELLATION_REASONS):
        raise ValueError("Invalid cancellation reasons")
    return value


def _adapter_result(value):
    if value is None:
        return None
    if not isinstance(value, dict) or value.get("outcome") not in {"accepted", "rejected_working", "unknown"}:
        raise ValueError("Invalid cancellation adapter result")
    fields = {"outcome", "receipt_id"} if value["outcome"] == "accepted" else {"outcome", "reason"}
    if set(value) != fields:
        raise ValueError("Cancellation adapter result fields do not match its outcome")
    store._identity(value.get("receipt_id", value.get("reason")), "cancellation adapter result")
    return deepcopy(value)


def _record(raw):
    value = store.decode(raw) if not isinstance(raw, dict) else deepcopy(raw)
    if not isinstance(value, dict) or set(value) != RECORD_FIELDS or value["schema"] != RECORD_SCHEMA:
        raise ValueError("Invalid cancellation operation")
    request = _request(value["request"])
    for field in ("operation_id", "owner_id"):
        if value[field] != request[field]:
            raise ValueError("Cancellation operation identity disagrees with request")
    if value["writer_epoch"] != request["writer_epoch"]:
        raise ValueError("Cancellation operation epoch disagrees with request")
    if value["request_sha256"] != store.digest(request) or value["command_sha256"] != store.digest(value["command"]):
        raise ValueError("Cancellation operation digest mismatch")
    expected_command = {
        "schema": "synthetic-cancel-command-v1", "operation_id": request["operation_id"],
        "account_id": request["account_id"], "environment": "synthetic",
        "target_client_order_id": request["target_client_order_id"],
        "target_order_id": request["target_order_id"], "writer_epoch": request["writer_epoch"],
    }
    if value["command"] != expected_command:
        raise ValueError("Cancellation command disagrees with request")
    if value["target_source"] not in ("entry", "reducing") or value["target_side"] not in ("buy", "sell"):
        raise ValueError("Invalid cancellation target binding")
    if value["state"] not in ACTIVE_STATES | TERMINAL_STATES:
        raise ValueError("Invalid cancellation operation state")
    result = _adapter_result(value["adapter_result"])
    store._timestamp_string(value["marked_at"], "cancellation marker time")
    if value["resolved_at"] is not None:
        store._timestamp_string(value["resolved_at"], "cancellation resolution time")
    store._version(value["last_event_version"], "cancellation event version")
    if value["state"] == "cancel_pending" and result is not None:
        raise ValueError("Pending cancellation cannot have an adapter result")
    if value["state"] in ACTIVE_STATES and value["resolved_at"] is not None:
        raise ValueError("Unresolved cancellation cannot have a resolution time")
    if value["state"] in TERMINAL_STATES and value["resolved_at"] is None:
        raise ValueError("Resolved cancellation requires a resolution time")
    if value["marked_at"] != utc(request["at"]).isoformat():
        raise ValueError("Cancellation marker time disagrees with request")
    return value


def _reasons(records, incidents):
    reasons = set()
    for record in records.values():
        reasons.update({"cancel_pending": {"cancellation_pending"},
                        "accepted": {"cancellation_reconciliation_required"},
                        "unknown": {"cancellation_unknown"}}.get(record["state"], set()))
    if incidents:
        reasons.add("cancellation_identity_conflict")
    return sorted(reasons)


def _read(connection):
    if connection.execute("PRAGMA user_version").fetchone()[0] != store.REDUCING_DATABASE_VERSION:
        raise ValueError("Cancellation requires a fresh v4 order database")
    row = connection.execute("SELECT payload FROM cancellation_state WHERE id=1").fetchone()
    if row is None:
        raise ValueError("Cancellation state missing; fresh v4 initialization required")
    stored = _state(row[0])
    baseline = store._parse_state(connection.execute(
        "SELECT payload FROM reducing_allocation_baseline WHERE id=1").fetchone()[0])
    if stored["account_id"] != baseline["account_id"]:
        raise ValueError("Cancellation baseline account mismatch")
    projected = {**stored, "version": 0, "as_of": utc(baseline["at"]).isoformat(),
                 "unresolved_reasons": []}
    projected = _state(projected)
    records, incidents, events = {}, {}, []
    _, _, writer_events = order_writer._read_writer(connection)
    writer_by_digest = {store.digest(event): event for event in writer_events}
    last_at = utc(baseline["at"])
    for expected, row in enumerate(connection.execute(
            "SELECT sequence,event_id,kind,input_sha256,payload_sha256,payload "
            "FROM cancellation_events ORDER BY sequence"), 1):
        sequence, event_id, kind, input_sha, payload_sha, raw = row
        event = store.decode(raw)
        if (sequence != expected or kind not in ("marked", "result", "evidence", "incident")
                or not isinstance(event, dict) or set(event) != EVENT_FIELDS
                or event["schema"] != EVENT_SCHEMA or event["event_id"] != event_id
                or event["kind"] != kind or event["committed_version"] != sequence
                or event["input_sha256"] != input_sha
                or store.digest(event["input"]) != input_sha or store.digest(event) != payload_sha):
            raise ValueError("Invalid cancellation event")
        base = {key: value for key, value in event.items() if key != "event_id"}
        if event_id != store.digest(base):
            raise ValueError("Cancellation event identity mismatch")
        event_at = store._timestamp_string(event["at"], "cancellation event time")
        if event_at < last_at:
            raise ValueError("Cancellation event time moved backwards")
        writer_event = writer_by_digest.get(event["writer_evidence_sha256"])
        if writer_event is None:
            raise ValueError("Cancellation event writer evidence is missing")
        record = None if event["record"] is None else _record(event["record"])
        incident = event["incident"]
        if kind == "incident":
            if record is not None or not isinstance(incident, dict):
                raise ValueError("Invalid cancellation incident event")
            incident_id = incident.get("incident_id")
            request = _request(incident.get("request"))
            if (set(incident) != {"incident_id", "request", "request_sha256", "matches"}
                    or incident["request_sha256"] != store.digest(request)
                    or incident_id != "cancel-conflict-" + store.digest({
                        "request": request, "request_sha256": incident["request_sha256"],
                        "matches": incident["matches"]})[:32]
                    or event["input"] != request
                    or not isinstance(incident["matches"], list)
                    or incident["matches"] != sorted(set(incident["matches"]))
                    or not incident["matches"]
                    or not set(incident["matches"]) <= set(records)):
                raise ValueError("Invalid cancellation incident")
            incidents[incident_id] = incident
        else:
            if incident is not None or record is None:
                raise ValueError("Invalid cancellation operation event")
            prior = records.get(record["operation_id"])
            if kind == "marked" and prior is not None:
                raise ValueError("Duplicate cancellation marker in journal")
            if kind != "marked" and prior is None:
                raise ValueError("Cancellation transition has no marker")
            if record["last_event_version"] != sequence:
                raise ValueError("Cancellation record event version mismatch")
            if kind == "marked":
                source, target = _historical_target(connection, record["request"])
                if (record["state"] != "cancel_pending" or record["adapter_result"] is not None
                        or record["request"] != event["input"]
                        or record["request"]["expected_cancellation_version"] != sequence - 1
                        or record["marked_at"] != event["at"]
                        or (record["target_source"], record["target_side"]) !=
                        (source, target["side"])
                        or target["state"] not in ("working", "unknown")):
                    raise ValueError("Invalid cancellation marker transition")
            elif kind == "result":
                if (prior["adapter_result"] is not None
                        or record["adapter_result"] != _adapter_result(event["input"])
                        or any(record[key] != prior[key] for key in RECORD_FIELDS - {
                            "state", "adapter_result", "resolved_at", "last_event_version"})):
                    raise ValueError("Invalid cancellation result transition")
                expected_state = (prior["state"] if prior["state"] in TERMINAL_STATES
                                  else record["adapter_result"]["outcome"])
                if record["state"] != expected_state:
                    raise ValueError("Cancellation result changed order evidence")
            elif kind == "evidence":
                evidence = event["input"]
                if (not isinstance(evidence, dict) or set(evidence) != {"evidence_id", "target"}
                        or any(record[key] != prior[key] for key in RECORD_FIELDS - {
                            "state", "resolved_at", "last_event_version"})):
                    raise ValueError("Invalid cancellation evidence transition")
                target = evidence["target"]
                expected_state = ("moot_filled" if target.get("state") == "filled" else
                                  "confirmed_cancelled" if target.get("state") == "cancelled" else
                                  "rejected_working" if (prior["state"] == "unknown"
                                                         and target.get("state") == "working") else None)
                if (record["state"] != expected_state
                        or (target.get("client_order_id"), target.get("order_id")) !=
                        (record["request"]["target_client_order_id"],
                         record["request"]["target_order_id"])):
                    raise ValueError("Cancellation evidence does not prove its transition")
                _verify_evidence_binding(connection, record, evidence)
            records[record["operation_id"]] = record
        expected_reasons = _reasons(records, incidents)
        expected_writer_request = order_reconciliation._writer_reconciliation_request(
            "cancel-" + (record["operation_id"] if record is not None
                         else event["input"]["operation_id"]),
            event_at, projected["unresolved_reasons"], expected_reasons)
        if (writer_event["kind"] != "reconciliation_disarmed"
                or writer_event["request"] != expected_writer_request
                or writer_event["at"] != event["at"]):
            raise ValueError("Cancellation writer fencing binding mismatch")
        projected = _state(event["state"])
        if (projected["version"] != sequence or projected["as_of"] != event_at.isoformat()
                or projected["account_id"] != stored["account_id"]
                or projected["unresolved_reasons"] != expected_reasons):
            raise ValueError("Cancellation event projection mismatch")
        events.append(event)
        last_at = event_at
    sql_records = {}
    for operation_id, client_id, order_id, request_sha, raw in connection.execute(
            "SELECT operation_id,target_client_order_id,target_order_id,request_sha256,payload "
            "FROM cancellation_operations"):
        record = _record(raw)
        request = record["request"]
        if (operation_id, client_id, order_id, request_sha) != (
                record["operation_id"], request["target_client_order_id"],
                request["target_order_id"], record["request_sha256"]):
            raise ValueError("Cancellation operation SQL identity mismatch")
        sql_records[operation_id] = record
    if records != sql_records:
        raise ValueError("Cancellation operations disagree with journal")
    sql_incidents = {}
    for incident_id, request_sha, raw in connection.execute(
            "SELECT incident_id,request_sha256,payload FROM cancellation_incidents"):
        incident = store.decode(raw)
        if (incident_id != incident.get("incident_id")
                or request_sha != incident.get("request_sha256")):
            raise ValueError("Cancellation incident SQL identity mismatch")
        sql_incidents[incident_id] = incident
    if incidents != sql_incidents or stored != projected:
        raise ValueError("Cancellation state disagrees with journal")
    return stored, records, incidents, events


def _verify_evidence_binding(connection, record, evidence):
    request = record["request"]
    snapshot = None
    if record["target_source"] == "entry":
        snapshots = [order_reconciliation._snapshot(store.decode(row[0])) for row in
                     connection.execute("SELECT payload FROM reconciliation_inbox")]
        snapshot = next((item for item in snapshots
                         if item["reconciliation_id"] == evidence["evidence_id"]), None)
    if snapshot is not None:
        targets = [{"client_order_id": item["client_order_id"],
                    "order_id": item["broker_order_id"], "side": "buy",
                    "state": item["state"], "original_quantity": item["original_quantity"],
                    "cumulative_executed_quantity": item["cumulative_executed_quantity"]}
                   for item in snapshot["orders"]]
    else:
        # An entry target may first be mapped by the entry journal and later
        # become terminal in cumulative reducing evidence. Bind the resolution
        # to its actual retained snapshot, not the marker's historical source.
        from . import order_sell_reconciliation
        row = connection.execute(
            "SELECT payload FROM reducing_reconciliation_inbox WHERE reconciliation_id=?",
            (evidence["evidence_id"],)).fetchone()
        if row is None:
            raise ValueError("Cancellation reducing evidence is missing")
        targets = order_sell_reconciliation._snapshot(store.decode(row[0]))["orders"]
    target = next((item for item in targets if (
        item["client_order_id"], item["order_id"]) ==
        (request["target_client_order_id"], request["target_order_id"])), None)
    if target != evidence["target"]:
        raise ValueError("Cancellation evidence disagrees with retained snapshot")


def _historical_target(connection, request):
    """Reconstruct the exact target visible at the request's bound versions."""
    from . import order_sell_reconciliation
    entry_state, entry_events = order_reconciliation._read(connection)
    reducing_state, reducing_events = order_sell_reconciliation._read(connection)
    entry_version = request["expected_entry_reconciliation_version"]
    reducing_version = request["expected_reducing_reconciliation_version"]
    if entry_version > entry_state["version"] or reducing_version > reducing_state["version"]:
        raise ValueError("Cancellation target versions are unavailable")
    entry_projection = (None if entry_version == 0
                        else entry_events[entry_version - 1]["state"]["order_projection"])
    reducing_orders = ([] if reducing_version == 0
                       else reducing_events[reducing_version - 1]["state"]["orders"])
    identity = (request["target_client_order_id"], request["target_order_id"])
    match = next((row for row in reducing_orders
                  if (row["client_order_id"], row["order_id"]) == identity), None)
    if match is not None:
        return "reducing", match
    if entry_projection is not None and (
            entry_projection["client_order_id"], entry_projection["broker_order_id"]) == identity:
        return "entry", {
            "client_order_id": entry_projection["client_order_id"],
            "order_id": entry_projection["broker_order_id"], "side": "buy",
            "state": entry_projection["state"],
            "original_quantity": entry_projection["original_quantity"],
            "cumulative_executed_quantity": entry_projection["executed_quantity"],
        }
    raise ValueError("Cancellation target is absent from its bound evidence versions")


def _append(connection, kind, at, input_value, writer_event, state, *, record=None, incident=None):
    state = deepcopy(state)
    state.update(version=state["version"] + 1, as_of=at.isoformat())
    if record is not None:
        record = deepcopy(record)
        record["last_event_version"] = state["version"]
    base = {
        "schema": EVENT_SCHEMA, "kind": kind, "at": at.isoformat(),
        "committed_version": state["version"], "input_sha256": store.digest(input_value),
        "input": deepcopy(input_value),
        "writer_evidence_sha256": store.digest(writer_event), "record": record,
        "incident": incident, "state": state,
    }
    event = {**base, "event_id": store.digest(base)}
    connection.execute("INSERT INTO cancellation_events VALUES (?, ?, ?, ?, ?, ?)",
                       (state["version"], event["event_id"], kind, store.digest(input_value),
                        store.digest(event), store.pack(event)))
    connection.execute("UPDATE cancellation_state SET payload=? WHERE id=1", (store.pack(state),))
    if record is not None:
        request = record["request"]
        connection.execute(
            "INSERT INTO cancellation_operations VALUES (?, ?, ?, ?, ?) "
            "ON CONFLICT(operation_id) DO UPDATE SET payload=excluded.payload",
            (record["operation_id"], request["target_client_order_id"],
             request["target_order_id"], record["request_sha256"], store.pack(record)))
    if incident is not None:
        connection.execute("INSERT INTO cancellation_incidents VALUES (?, ?, ?)",
                           (incident["incident_id"], incident["request_sha256"], store.pack(incident)))
    return state, record, event


def _writer_transition(connection, operation_id, at, reasons):
    current, _, _ = order_writer._read_writer(connection)
    current_reasons = set(current["unresolved_reasons"])
    clear = sorted(current_reasons & CANCELLATION_REASONS)
    order_reconciliation._disarm(connection, "cancel-" + operation_id, at, reasons, clear)
    return order_writer._read_writer(connection)[2][-1]


def _target(connection, request):
    from . import order_sell_reconciliation
    entry, _ = order_reconciliation._read(connection)
    reducing, _ = order_sell_reconciliation._read(connection)
    matches = [row for row in reducing["orders"]
               if (row["client_order_id"], row["order_id"]) ==
               (request["target_client_order_id"], request["target_order_id"])]
    if matches:
        return "reducing", matches[0], entry, reducing
    projection = entry["order_projection"]
    if projection is not None and (projection["client_order_id"], projection["broker_order_id"]) == (
            request["target_client_order_id"], request["target_order_id"]):
        return "entry", {
            "client_order_id": projection["client_order_id"],
            "order_id": projection["broker_order_id"], "side": "buy",
            "state": projection["state"], "original_quantity": projection["original_quantity"],
            "cumulative_executed_quantity": projection["executed_quantity"],
        }, entry, reducing
    raise ValueError("Cancellation target is not present in cumulative evidence")


def mark(path, raw):
    request = _request(raw)
    at, expires = utc(request["at"]), utc(request["expires_at"])
    with store.database(path, write=True) as connection:
        account = store._read_state(connection)
        state, records, incidents, events = _read(connection)
        current_writer, _, writer_events = order_writer._read_writer(connection)
        existing = records.get(request["operation_id"])
        if existing is not None and existing["request"] == request:
            return _operation_report(state, existing, duplicate=True)
        conflicts = []
        if existing is not None:
            conflicts.append(existing["operation_id"])
        conflicts.extend(row["operation_id"] for row in records.values()
                         if (row["request"]["target_client_order_id"], row["request"]["target_order_id"]) ==
                         (request["target_client_order_id"], request["target_order_id"])
                         and row["state"] in ACTIVE_STATES)
        if conflicts:
            incident = {"request": request, "request_sha256": store.digest(request),
                        "matches": sorted(set(conflicts))}
            incident["incident_id"] = "cancel-conflict-" + store.digest(incident)[:32]
            prior = incidents.get(incident["incident_id"])
            if prior is not None:
                return _operation_report(state, None, duplicate=True, outcome="identity_conflict")
            event_at = max(at, utc(state["as_of"]), utc(writer_events[-1]["at"]))
            reasons = sorted(set(state["unresolved_reasons"] + ["cancellation_identity_conflict"]))
            writer_event = _writer_transition(connection, request["operation_id"], event_at, reasons)
            state.update(unresolved_reasons=reasons)
            state, _, _ = _append(connection, "incident", event_at, request,
                                  writer_event, state, incident=incident)
            return _operation_report(state, None, duplicate=False, outcome="identity_conflict")
        source, target, entry, reducing = _target(connection, request)
        from . import order_allocations
        allocation = order_allocations._read(connection)[0]
        expected = (
            ("expected_account_version", account["version"]),
            ("expected_entry_reconciliation_version", entry["version"]),
            ("expected_reducing_reconciliation_version", reducing["version"]),
            ("expected_writer_version", current_writer["version"]),
            ("expected_allocation_version", allocation["version"]),
            ("expected_cancellation_version", state["version"]),
        )
        for field, actual in expected:
            if request[field] != actual:
                raise ValueError(field.replace("expected_", "").replace("_", " ") + " changed")
        if request["account_id"] != account["account_id"] or state["account_id"] != account["account_id"]:
            raise ValueError("Cancellation account mismatch")
        if current_writer["disarmed"] or current_writer["unresolved_reasons"]:
            raise ValueError("Writer is disarmed")
        if (current_writer["owner_id"], current_writer["epoch"]) != (request["owner_id"], request["writer_epoch"]):
            raise ValueError("Writer ownership or fencing epoch changed")
        if target["state"] not in ("working", "unknown"):
            raise ValueError("Cancellation target is already terminal")
        if not at < expires or expires - at > timedelta(seconds=60):
            raise ValueError("Cancellation authority expiry is invalid")
        if (at < utc(account["at"]) or at < utc(state["as_of"])
                or (writer_events and at < utc(writer_events[-1]["at"]))):
            raise ValueError("Cancellation decision time moved backwards")
        if store._periods(at.isoformat()) != (account["session"], account["week"]):
            raise ValueError("Cancellation requires a reviewed period transition")
        command = {
            "schema": "synthetic-cancel-command-v1", "operation_id": request["operation_id"],
            "account_id": request["account_id"], "environment": "synthetic",
            "target_client_order_id": request["target_client_order_id"],
            "target_order_id": request["target_order_id"], "writer_epoch": request["writer_epoch"],
        }
        record = {
            "schema": RECORD_SCHEMA, "operation_id": request["operation_id"],
            "request": request, "request_sha256": store.digest(request), "command": command,
            "command_sha256": store.digest(command), "target_source": source,
            "target_side": target["side"], "state": "cancel_pending", "adapter_result": None,
            "marked_at": at.isoformat(), "resolved_at": None, "owner_id": request["owner_id"],
            "writer_epoch": request["writer_epoch"], "last_event_version": 0,
        }
        reasons = sorted(set(state["unresolved_reasons"] + ["cancellation_pending"]))
        writer_event = _writer_transition(connection, request["operation_id"], at, reasons)
        state.update(unresolved_reasons=reasons)
        state, record, _ = _append(connection, "marked", at, request,
                                   writer_event, state, record=record)
        return _operation_report(state, record, duplicate=False)


def _record_result(path, operation_id, owner_id, writer_epoch, at, result):
    _adapter_result(result)
    with store.database(path, write=True) as connection:
        store._read_state(connection)
        state, records, incidents, events = _read(connection)
        result_at = utc(at)
        record = records.get(operation_id)
        if record is None or record["adapter_result"] is not None:
            raise ValueError("Cancellation is not awaiting an adapter result")
        if (record["owner_id"], record["writer_epoch"]) != (owner_id, writer_epoch):
            raise ValueError("Cancellation result fencing identity changed")
        if result_at < utc(state["as_of"]):
            raise ValueError("Cancellation result time moved backwards")
        record = deepcopy(record)
        record["adapter_result"] = deepcopy(result)
        if record["state"] == "cancel_pending":
            record["state"] = result["outcome"]
            if record["state"] == "rejected_working":
                record["resolved_at"] = result_at.isoformat()
        reasons = _reasons({**records, operation_id: record}, incidents)
        writer_event = _writer_transition(connection, operation_id, result_at, reasons)
        state.update(unresolved_reasons=reasons)
        state, record, _ = _append(connection, "result", result_at, result,
                                   writer_event, state, record=record)
        return _operation_report(state, record, duplicate=False)


def apply_evidence(connection, at, targets, evidence_id):
    """Resolve marked cancellations from complete cumulative order evidence."""
    state, records, incidents, _ = _read(connection)
    at = at if hasattr(at, "isoformat") else utc(at)
    by_target = {(row["client_order_id"], row["order_id"]): row for row in targets}
    changed = []
    for operation_id in sorted(records):
        prior = records[operation_id]
        if prior["state"] not in ACTIVE_STATES:
            continue
        request = prior["request"]
        target = by_target.get((request["target_client_order_id"], request["target_order_id"]))
        if target is None:
            continue
        next_state = None
        if target["state"] == "filled":
            next_state = "moot_filled"
        elif target["state"] == "cancelled":
            next_state = "confirmed_cancelled"
        elif prior["state"] == "unknown" and target["state"] == "working":
            next_state = "rejected_working"
        if next_state is None:
            continue
        record = deepcopy(prior)
        record.update(state=next_state, resolved_at=at.isoformat())
        future = {**records, operation_id: record}
        reasons = _reasons(future, incidents)
        writer_event = _writer_transition(connection, operation_id, at, reasons)
        state.update(unresolved_reasons=reasons)
        state, record, _ = _append(connection, "evidence", at,
                                   {"evidence_id": evidence_id, "target": target},
                                   writer_event, state, record=record)
        records[operation_id] = record
        changed.append(operation_id)
    return changed


def dispatch_synthetic(path, payload, outcome, adapter=None, result_at=None):
    if outcome not in SYNTHETIC_OUTCOMES:
        raise ValueError("Unsupported synthetic cancellation outcome")
    adapter = adapter or SyntheticCancellationAdapter()
    marked = mark(path, payload)
    if not marked["should_call_adapter"]:
        return marked
    try:
        result = adapter.cancel(marked["operation"]["command"], outcome)
    except CancellationUncertain:
        result = {"outcome": "unknown", "reason": "lost_cancellation_response"}
    return _record_result(path, payload["operation_id"], payload["owner_id"],
                          payload["writer_epoch"], result_at or payload["at"], result)


def _operation_report(state, record, *, duplicate, outcome=None):
    return {
        "schema": REPORT_SCHEMA, "mode": MODE, "account_id": state["account_id"],
        "environment": state["environment"], "version": state["version"],
        "as_of": state["as_of"], "outcome": outcome or record["state"],
        "duplicate": duplicate, "should_call_adapter": False if duplicate or record is None
        else record["state"] == "cancel_pending" and record["adapter_result"] is None,
        "unresolved_reasons": state["unresolved_reasons"], "operation": deepcopy(record),
        "quantity_released": 0, "cash_released_usd": "0", "risk_released_gbp": "0",
        "live_trading_enabled": False,
    }


def status(path):
    with store.database(path) as connection:
        store._read_state(connection)
        state, records, incidents, _ = _read(connection)
        return {
            "schema": REPORT_SCHEMA, "mode": MODE, "account_id": state["account_id"],
            "environment": state["environment"], "version": state["version"],
            "as_of": state["as_of"], "unresolved_reasons": state["unresolved_reasons"],
            "operations": [records[key] for key in sorted(records)],
            "incident_count": len(incidents), "dispatch_authorized": False,
            "live_trading_enabled": False,
        }


def history(path):
    with store.database(path) as connection:
        store._read_state(connection)
        return _read(connection)[3]
