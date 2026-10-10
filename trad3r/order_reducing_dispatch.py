"""Fenced synthetic dispatch for allocated protective stops and reducing limits."""
from copy import deepcopy
from dataclasses import dataclass
from datetime import timedelta

from .ledger import utc
from .risk import money
from . import order_reconciliation, order_store as store, order_writer


REQUEST_SCHEMA = "reducing-dispatch-request-v1"
STATE_SCHEMA = "reducing-dispatch-state-v1"
RECORD_SCHEMA = "reducing-dispatch-operation-v1"
EVENT_SCHEMA = "reducing-dispatch-event-v1"
REPORT_SCHEMA = "reducing-dispatch-report-v1"
MODE = "synthetic_fenced_reducing_dispatch_only"
REQUEST_FIELDS = {
    "schema", "operation_id", "allocation_id", "account_id", "environment",
    "owner_id", "writer_epoch", "at", "expires_at", "order_type",
    "time_in_force", "limit_price_usd", "stop_price_usd",
    "expected_account_version", "expected_entry_reconciliation_version",
    "expected_reducing_reconciliation_version", "expected_writer_version",
    "expected_allocation_version", "expected_cancellation_version",
    "expected_dispatch_version",
}
RECORD_FIELDS = {
    "schema", "operation_id", "allocation_id", "request", "request_sha256",
    "command", "command_sha256", "state", "adapter_result", "broker_order_id",
    "marked_at", "resolved_at", "owner_id", "writer_epoch", "last_event_version",
}
EVENT_FIELDS = {
    "schema", "event_id", "kind", "at", "committed_version", "input_sha256",
    "input", "writer_evidence_sha256", "record", "incident", "state",
}
ACTIVE_STATES = {"submitting", "acknowledged", "unknown"}
EVIDENCED_STATES = {"working", "filled", "cancelled"}
TERMINAL_STATES = {"rejected", "filled", "cancelled"}
DISPATCH_REASONS = {
    "reducing_submission_pending", "reducing_reconciliation_required",
    "reducing_submission_unknown", "reducing_dispatch_identity_conflict",
}
SYNTHETIC_OUTCOMES = {"acknowledged", "rejected", "accept_then_timeout"}


class DispatchUncertain(RuntimeError):
    """The synthetic adapter accepted an order but lost its response."""


@dataclass
class SyntheticReducingAdapter:
    calls: int = 0

    def submit(self, command, outcome):
        self.calls += 1
        if outcome == "acknowledged":
            return {"outcome": "acknowledged",
                    "broker_order_id": "synthetic-" + store.digest(command)[:24]}
        if outcome == "rejected":
            return {"outcome": "rejected", "reason": "synthetic_order_rejected"}
        if outcome == "accept_then_timeout":
            raise DispatchUncertain("synthetic reducing-order response lost")
        raise ValueError("Unsupported synthetic reducing dispatch outcome")


def _initialize_tables(connection, account_id, at):
    state = {
        "schema": STATE_SCHEMA, "version": 0, "account_id": account_id,
        "environment": "synthetic", "as_of": at.isoformat(),
        "unresolved_reasons": [], "live_trading_enabled": False,
    }
    connection.execute("CREATE TABLE reducing_dispatch_state "
                       "(id INTEGER PRIMARY KEY CHECK(id=1), payload TEXT NOT NULL)")
    connection.execute("CREATE TABLE reducing_dispatch_operations "
                       "(operation_id TEXT PRIMARY KEY, allocation_id TEXT UNIQUE NOT NULL, "
                       "request_sha256 TEXT NOT NULL, payload TEXT NOT NULL)")
    connection.execute("CREATE TABLE reducing_dispatch_incidents "
                       "(incident_id TEXT PRIMARY KEY, request_sha256 TEXT NOT NULL, payload TEXT NOT NULL)")
    connection.execute("CREATE TABLE reducing_dispatch_events "
                       "(sequence INTEGER PRIMARY KEY, event_id TEXT UNIQUE NOT NULL, kind TEXT NOT NULL, "
                       "input_sha256 TEXT NOT NULL, payload_sha256 TEXT NOT NULL, payload TEXT NOT NULL)")
    connection.execute("INSERT INTO reducing_dispatch_state VALUES (1, ?)", (store.pack(state),))


def _request(raw):
    value = deepcopy(raw)
    if not isinstance(value, dict) or set(value) != REQUEST_FIELDS or value["schema"] != REQUEST_SCHEMA:
        raise ValueError("Reducing dispatch request fields do not match the contract")
    for field in ("operation_id", "allocation_id", "account_id", "owner_id"):
        store._identity(value[field], field.replace("_", " "))
    if value["environment"] != "synthetic":
        raise ValueError("Only synthetic reducing dispatch is supported")
    at = store._timestamp_string(value["at"], "reducing dispatch time")
    expires = store._timestamp_string(value["expires_at"], "reducing dispatch expiry")
    if not at < expires <= at + timedelta(seconds=60):
        raise ValueError("Reducing dispatch expiry must be within 60 seconds")
    for field in ("writer_epoch", "expected_account_version",
                  "expected_entry_reconciliation_version",
                  "expected_reducing_reconciliation_version", "expected_writer_version",
                  "expected_allocation_version", "expected_cancellation_version",
                  "expected_dispatch_version"):
        store._version(value[field], field.replace("_", " "))
    if value["time_in_force"] != "day" or value["order_type"] not in ("limit", "stop"):
        raise ValueError("Reducing dispatch supports day limit and protective stop orders only")
    for field in ("limit_price_usd", "stop_price_usd"):
        if value[field] is not None and money(store._decimal_string(value[field], field.replace("_", " "))) <= 0:
            raise ValueError("Reducing dispatch prices must be positive")
    if ((value["order_type"] == "limit" and
         (value["limit_price_usd"] is None or value["stop_price_usd"] is not None)) or
            (value["order_type"] == "stop" and
             (value["stop_price_usd"] is None or value["limit_price_usd"] is not None))):
        raise ValueError("Reducing dispatch price fields disagree with order type")
    return value


def _state(raw):
    value = store.decode(raw) if not isinstance(raw, dict) else deepcopy(raw)
    fields = {"schema", "version", "account_id", "environment", "as_of",
              "unresolved_reasons", "live_trading_enabled"}
    if (not isinstance(value, dict) or set(value) != fields or value["schema"] != STATE_SCHEMA
            or value["environment"] != "synthetic" or value["live_trading_enabled"] is not False):
        raise ValueError("Invalid reducing dispatch state")
    store._version(value["version"], "reducing dispatch version")
    store._identity(value["account_id"], "reducing dispatch account")
    store._timestamp_string(value["as_of"], "reducing dispatch state time")
    if (not isinstance(value["unresolved_reasons"], list)
            or value["unresolved_reasons"] != sorted(set(value["unresolved_reasons"]))
            or not set(value["unresolved_reasons"]) <= DISPATCH_REASONS):
        raise ValueError("Invalid reducing dispatch reasons")
    return value


def _adapter_result(value):
    if value is None:
        return None
    if not isinstance(value, dict) or value.get("outcome") not in ("acknowledged", "rejected", "unknown"):
        raise ValueError("Invalid reducing adapter result")
    fields = ({"outcome", "broker_order_id"} if value["outcome"] == "acknowledged"
              else {"outcome", "reason"})
    if set(value) != fields:
        raise ValueError("Reducing adapter result fields do not match its outcome")
    store._identity(value.get("broker_order_id", value.get("reason")), "reducing adapter result")
    return deepcopy(value)


def _allocation_row(connection, allocation_id):
    row = connection.execute("SELECT payload FROM reducing_allocations WHERE allocation_id=?",
                             (allocation_id,)).fetchone()
    if row is None:
        raise ValueError("Reducing dispatch allocation is missing")
    from . import order_allocations
    return order_allocations._record_payload(row[0])


def _expected_command(request, allocation):
    return {
        "schema": "synthetic-reducing-command-v1",
        "operation_id": request["operation_id"], "allocation_id": request["allocation_id"],
        "account_id": request["account_id"], "environment": "synthetic",
        "client_order_id": allocation["client_order_id"],
        "entry_intent_id": allocation["request"]["entry_intent_id"],
        "instrument_id": allocation["request"]["instrument_id"],
        "purpose": allocation["request"]["purpose"], "side": "sell",
        "quantity": allocation["quantity"], "fee_bound_usd": allocation["fee_bound_usd"],
        "order_type": request["order_type"], "time_in_force": request["time_in_force"],
        "limit_price_usd": request["limit_price_usd"], "stop_price_usd": request["stop_price_usd"],
        "writer_epoch": request["writer_epoch"],
    }


def _record(connection, raw):
    value = store.decode(raw) if not isinstance(raw, dict) else deepcopy(raw)
    if not isinstance(value, dict) or set(value) != RECORD_FIELDS or value["schema"] != RECORD_SCHEMA:
        raise ValueError("Invalid reducing dispatch operation")
    request = _request(value["request"])
    allocation = _allocation_row(connection, value["allocation_id"])
    if value["operation_id"] != request["operation_id"] or value["allocation_id"] != request["allocation_id"]:
        raise ValueError("Reducing dispatch identity disagrees with request")
    if (value["owner_id"], value["writer_epoch"]) != (request["owner_id"], request["writer_epoch"]):
        raise ValueError("Reducing dispatch fence disagrees with request")
    if value["request_sha256"] != store.digest(request):
        raise ValueError("Reducing dispatch request digest mismatch")
    command = _expected_command(request, allocation)
    if value["command"] != command or value["command_sha256"] != store.digest(command):
        raise ValueError("Reducing dispatch command binding mismatch")
    if value["state"] not in ACTIVE_STATES | EVIDENCED_STATES | {"rejected", "conflict"}:
        raise ValueError("Invalid reducing dispatch operation state")
    result = _adapter_result(value["adapter_result"])
    store._timestamp_string(value["marked_at"], "reducing dispatch marker time")
    if value["resolved_at"] is not None:
        store._timestamp_string(value["resolved_at"], "reducing dispatch resolution time")
    store._version(value["last_event_version"], "reducing dispatch event version")
    if value["marked_at"] != utc(request["at"]).isoformat():
        raise ValueError("Reducing dispatch marker time disagrees with request")
    if value["state"] == "submitting" and result is not None:
        raise ValueError("Pending reducing dispatch cannot have an adapter result")
    if value["broker_order_id"] is not None:
        store._identity(value["broker_order_id"], "reducing dispatch broker order")
    if value["state"] == "submitting" and (value["broker_order_id"] is not None
                                             or value["resolved_at"] is not None):
        raise ValueError("Pending reducing dispatch has terminal evidence")
    if value["state"] == "acknowledged" and (result is None
                                               or result["outcome"] != "acknowledged"
                                               or value["broker_order_id"] != result["broker_order_id"]
                                               or value["resolved_at"] is not None):
        raise ValueError("Acknowledged reducing dispatch is inconsistent")
    if value["state"] == "rejected" and (result is None or result["outcome"] != "rejected"
                                          or value["broker_order_id"] is not None):
        raise ValueError("Rejected reducing dispatch is inconsistent")
    if value["state"] == "unknown" and value["resolved_at"] is not None:
        raise ValueError("Unknown reducing dispatch cannot be resolved")
    if value["state"] == "working" and (value["broker_order_id"] is None
                                         or value["resolved_at"] is not None):
        raise ValueError("Working reducing dispatch evidence is inconsistent")
    if value["state"] in ("filled", "cancelled") and value["broker_order_id"] is None:
        raise ValueError("Terminal reducing dispatch is missing broker identity")
    if value["state"] == "conflict" and value["resolved_at"] is not None:
        raise ValueError("Conflicting reducing dispatch cannot be resolved")
    if value["state"] in TERMINAL_STATES and value["resolved_at"] is None:
        raise ValueError("Terminal reducing dispatch requires resolution time")
    return value


def _reasons(records, incidents):
    reasons = set()
    for record in records.values():
        reasons.update({"submitting": {"reducing_submission_pending"},
                        "acknowledged": {"reducing_reconciliation_required"},
                        "unknown": {"reducing_submission_unknown"},
                        "conflict": {"reducing_dispatch_identity_conflict"}}.get(
                            record["state"], set()))
    if incidents:
        reasons.add("reducing_dispatch_identity_conflict")
    return sorted(reasons)


def _read(connection):
    if connection.execute("PRAGMA user_version").fetchone()[0] != store.REDUCING_DATABASE_VERSION:
        raise ValueError("Reducing dispatch requires a fresh v4 order database")
    row = connection.execute("SELECT payload FROM reducing_dispatch_state WHERE id=1").fetchone()
    if row is None:
        raise ValueError("Reducing dispatch state missing; fresh v4 initialization required")
    stored = _state(row[0])
    baseline = store._parse_state(connection.execute(
        "SELECT payload FROM reducing_allocation_baseline WHERE id=1").fetchone()[0])
    if stored["account_id"] != baseline["account_id"]:
        raise ValueError("Reducing dispatch baseline account mismatch")
    projected = _state({**stored, "version": 0, "as_of": utc(baseline["at"]).isoformat(),
                        "unresolved_reasons": []})
    _, _, writer_events = order_writer._read_writer(connection)
    writer_by_sha = {store.digest(event): event for event in writer_events}
    records, incidents, events = {}, {}, []
    last_at = utc(baseline["at"])
    for expected, row in enumerate(connection.execute(
            "SELECT sequence,event_id,kind,input_sha256,payload_sha256,payload "
            "FROM reducing_dispatch_events ORDER BY sequence"), 1):
        sequence, event_id, kind, input_sha, payload_sha, raw = row
        event = store.decode(raw)
        if (sequence != expected or kind not in ("marked", "result", "evidence", "incident")
                or not isinstance(event, dict) or set(event) != EVENT_FIELDS
                or event["schema"] != EVENT_SCHEMA or event["event_id"] != event_id
                or event["kind"] != kind or event["committed_version"] != sequence
                or event["input_sha256"] != input_sha or store.digest(event["input"]) != input_sha
                or store.digest(event) != payload_sha):
            raise ValueError("Invalid reducing dispatch event")
        base = {key: value for key, value in event.items() if key != "event_id"}
        writer_event = writer_by_sha.get(event["writer_evidence_sha256"])
        if event_id != store.digest(base) or writer_event is None:
            raise ValueError("Reducing dispatch event evidence mismatch")
        event_at = store._timestamp_string(event["at"], "reducing dispatch event time")
        if event_at < last_at:
            raise ValueError("Reducing dispatch event time moved backwards")
        last_at = event_at
        record = None if event["record"] is None else _record(connection, event["record"])
        incident = event["incident"]
        if kind == "incident":
            if (record is not None or not isinstance(incident, dict)
                    or set(incident) != {"incident_id", "request", "request_sha256", "matches"}):
                raise ValueError("Invalid reducing dispatch incident event")
            incident_request = _request(incident["request"])
            incident_id = store._identity(incident.get("incident_id"), "dispatch incident")
            identity = {"request": incident_request,
                        "request_sha256": store.digest(incident_request),
                        "matches": incident["matches"]}
            matches = sorted(set(
                row["operation_id"] for row in records.values()
                if row["operation_id"] == incident_request["operation_id"]
                or row["allocation_id"] == incident_request["allocation_id"]))
            if (incident_id in incidents or incident["request"] != incident_request
                    or incident["request_sha256"] != identity["request_sha256"]
                    or incident["matches"] != matches or not matches
                    or incident_id != "dispatch-conflict-" + store.digest(identity)[:32]):
                raise ValueError("Invalid reducing dispatch incident")
            incidents[incident_id] = deepcopy(incident)
        else:
            if incident is not None or record is None:
                raise ValueError("Invalid reducing dispatch operation event")
            prior = records.get(record["operation_id"])
            if kind == "marked" and (prior is not None or record["state"] != "submitting"):
                raise ValueError("Invalid reducing dispatch marker transition")
            if kind == "marked" and event["input"] != record["request"]:
                raise ValueError("Reducing dispatch marker input mismatch")
            if kind != "marked" and prior is None:
                raise ValueError("Reducing dispatch result has no marker")
            if record["last_event_version"] != sequence:
                raise ValueError("Reducing dispatch record version mismatch")
            if kind == "result":
                expected_record = _result_record(prior, event["input"], event_at)
                expected_record["last_event_version"] = sequence
                if record != expected_record:
                    raise ValueError("Invalid reducing dispatch result transition")
            if kind == "evidence":
                evidence = event["input"]
                if isinstance(evidence, dict):
                    store._identity(evidence.get("evidence_id"), "dispatch evidence")
                expected_record = (_evidence_record(prior, evidence["order"], event_at)
                                   if isinstance(evidence, dict)
                                   and set(evidence) == {"evidence_id", "order"} else None)
                if expected_record is not None:
                    expected_record["last_event_version"] = sequence
                if expected_record is None or record != expected_record:
                    raise ValueError("Invalid reducing dispatch evidence transition")
            records[record["operation_id"]] = record
        expected_reasons = _reasons(records, incidents)
        expected_state = _state({**event["state"], "version": sequence})
        if (expected_state["version"] != sequence or expected_state["as_of"] != event["at"]
                or expected_state["account_id"] != baseline["account_id"]
                or expected_state["unresolved_reasons"] != expected_reasons):
            raise ValueError("Reducing dispatch event state mismatch")
        if (writer_event["kind"] != "reconciliation_disarmed"
                or writer_event["at"] != event["at"]
                or writer_event["request"]["reconciliation_id"] !=
                    "reduce-" + event["input"].get("operation_id", record["operation_id"] if record else "")
                or not writer_event["writer"]["disarmed"]
                or sorted(set(writer_event["writer"]["unresolved_reasons"]) & DISPATCH_REASONS)
                    != expected_reasons):
            raise ValueError("Reducing dispatch writer transition mismatch")
        projected = expected_state
        events.append(event)
    table_records = {}
    for operation_id, allocation_id, request_sha, raw in connection.execute(
            "SELECT operation_id,allocation_id,request_sha256,payload FROM reducing_dispatch_operations"):
        record = _record(connection, raw)
        if (operation_id, allocation_id, request_sha) != (
                record["operation_id"], record["allocation_id"], record["request_sha256"]):
            raise ValueError("Reducing dispatch SQL identity mismatch")
        table_records[operation_id] = record
    table_incidents = {}
    for incident_id, request_sha, raw in connection.execute(
            "SELECT incident_id,request_sha256,payload FROM reducing_dispatch_incidents"):
        incident = store.decode(raw)
        if incident_id != incident.get("incident_id") or request_sha != incident.get("request_sha256"):
            raise ValueError("Reducing dispatch incident SQL identity mismatch")
        table_incidents[incident_id] = incident
    if table_records != records or table_incidents != incidents or projected != stored:
        raise ValueError("Reducing dispatch projection disagrees with journal")
    return stored, records, incidents, events


def _append(connection, kind, at, input_value, writer_event, state, *, record=None, incident=None):
    state = deepcopy(state)
    state.update(version=state["version"] + 1, as_of=at.isoformat())
    if record is not None:
        record = deepcopy(record)
        record["last_event_version"] = state["version"]
    state["unresolved_reasons"] = _reasons(
        {row[0]: _record(connection, row[1]) for row in connection.execute(
            "SELECT operation_id,payload FROM reducing_dispatch_operations")}
        | ({record["operation_id"]: record} if record is not None else {}),
        {row[0]: store.decode(row[1]) for row in connection.execute(
            "SELECT incident_id,payload FROM reducing_dispatch_incidents")}
        | ({incident["incident_id"]: incident} if incident is not None else {}))
    base = {"schema": EVENT_SCHEMA, "kind": kind, "at": at.isoformat(),
            "committed_version": state["version"], "input_sha256": store.digest(input_value),
            "input": deepcopy(input_value), "writer_evidence_sha256": store.digest(writer_event),
            "record": record, "incident": incident, "state": state}
    event = {**base, "event_id": store.digest(base)}
    connection.execute("INSERT INTO reducing_dispatch_events VALUES (?, ?, ?, ?, ?, ?)",
                       (state["version"], event["event_id"], kind, store.digest(input_value),
                        store.digest(event), store.pack(event)))
    connection.execute("UPDATE reducing_dispatch_state SET payload=? WHERE id=1", (store.pack(state),))
    if record is not None:
        connection.execute("INSERT INTO reducing_dispatch_operations VALUES (?, ?, ?, ?) "
                           "ON CONFLICT(operation_id) DO UPDATE SET payload=excluded.payload",
                           (record["operation_id"], record["allocation_id"],
                            record["request_sha256"], store.pack(record)))
    if incident is not None:
        connection.execute("INSERT INTO reducing_dispatch_incidents VALUES (?, ?, ?)",
                           (incident["incident_id"], incident["request_sha256"], store.pack(incident)))
    return state, record, event


def _writer_transition(connection, operation_id, at, reasons):
    current, _, _ = order_writer._read_writer(connection)
    clear = sorted(set(current["unresolved_reasons"]) & DISPATCH_REASONS)
    order_reconciliation._disarm(connection, "reduce-" + operation_id, at, reasons, clear)
    return order_writer._read_writer(connection)[2][-1]


def _result_record(prior, result, at):
    _adapter_result(result)
    record = deepcopy(prior)
    record["adapter_result"] = deepcopy(result)
    if prior["state"] == "submitting":
        record["state"] = result["outcome"]
        if result["outcome"] == "acknowledged":
            record["broker_order_id"] = result["broker_order_id"]
        elif result["outcome"] == "rejected":
            record["resolved_at"] = at.isoformat()
    elif result["outcome"] == "rejected" or (
            result["outcome"] == "acknowledged"
            and record["broker_order_id"] != result["broker_order_id"]):
        record.update(state="conflict", resolved_at=None)
    return record


def _evidence_record(prior, target, at):
    required = {"client_order_id", "order_id", "side", "state",
                "original_quantity", "cumulative_executed_quantity"}
    if (not isinstance(target, dict) or set(target) != required or target["side"] != "sell"
            or target["client_order_id"] != prior["command"]["client_order_id"]
            or target["original_quantity"] != prior["command"]["quantity"]
            or target["state"] not in EVIDENCED_STATES | {"unknown"}
            or (prior["broker_order_id"] is not None
                and target["order_id"] != prior["broker_order_id"])):
        raise ValueError("Reducing dispatch evidence does not match its command")
    record = deepcopy(prior)
    record["broker_order_id"] = target["order_id"]
    record["state"] = target["state"]
    if target["state"] in ("filled", "cancelled"):
        record["resolved_at"] = at.isoformat()
    return record


def _report(state, records, *, record=None, duplicate=False, outcome=None):
    ordered = [deepcopy(records[key]) for key in sorted(records)]
    return {"schema": REPORT_SCHEMA, "mode": MODE, "account_id": state["account_id"],
            "environment": state["environment"], "version": state["version"],
            "as_of": state["as_of"], "outcome": outcome or (record["state"] if record else "ready"),
            "duplicate": duplicate,
            "should_call_adapter": bool(record and not duplicate and record["state"] == "submitting"),
            "unresolved_reasons": state["unresolved_reasons"], "operation": deepcopy(record),
            "operations": ordered, "live_trading_enabled": False}


def status(path):
    with store.database(path) as connection:
        store._read_state(connection)
        state, records, _, _ = _read(connection)
        return _report(state, records)


def mark(path, raw):
    request = _request(raw)
    at, expires = utc(request["at"]), utc(request["expires_at"])
    with store.database(path, write=True) as connection:
        account = store._read_state(connection)
        state, records, incidents, _ = _read(connection)
        current_writer, _, writer_events = order_writer._read_writer(connection)
        existing = records.get(request["operation_id"])
        if existing is not None and existing["request"] == request:
            return _report(state, records, record=existing, duplicate=True)
        matches = ([existing] if existing is not None else []) + [
            row for row in records.values() if row["allocation_id"] == request["allocation_id"]]
        if matches:
            incident = {"request": request, "request_sha256": store.digest(request),
                        "matches": sorted(set(row["operation_id"] for row in matches))}
            incident["incident_id"] = "dispatch-conflict-" + store.digest(incident)[:32]
            if incident["incident_id"] in incidents:
                return _report(state, records, duplicate=True, outcome="identity_conflict")
            event_at = max(at, utc(state["as_of"]), utc(writer_events[-1]["at"]))
            reasons = sorted(set(state["unresolved_reasons"] + ["reducing_dispatch_identity_conflict"]))
            writer_event = _writer_transition(connection, request["operation_id"], event_at, reasons)
            state, _, _ = _append(connection, "incident", event_at, request, writer_event,
                                  state, incident=incident)
            return _report(state, records, duplicate=False, outcome="identity_conflict")
        from . import order_allocations, order_cancellation, order_sell_reconciliation
        allocation_state, allocation_records, _ = order_allocations._read(connection)
        cancellation_state, _, _, _ = order_cancellation._read(connection)
        entry_state, _ = order_reconciliation._read(connection)
        sell_state, _ = order_sell_reconciliation._read(connection)
        allocation = next((row for row in allocation_records
                           if row["allocation_id"] == request["allocation_id"]), None)
        expected = (("expected_account_version", account["version"]),
                    ("expected_entry_reconciliation_version", entry_state["version"]),
                    ("expected_reducing_reconciliation_version", sell_state["version"]),
                    ("expected_writer_version", current_writer["version"]),
                    ("expected_allocation_version", allocation_state["version"]),
                    ("expected_cancellation_version", cancellation_state["version"]),
                    ("expected_dispatch_version", state["version"]))
        for field, actual in expected:
            if request[field] != actual:
                raise ValueError(field.replace("expected_", "").replace("_", " ") + " changed")
        if request["account_id"] != account["account_id"] or state["account_id"] != account["account_id"]:
            raise ValueError("Reducing dispatch account mismatch")
        if allocation is None or allocation["state"] != "reserved":
            raise ValueError("Reducing dispatch requires a reserved allocation")
        purpose = allocation["request"]["purpose"]
        if ((purpose == "reducing_exit" and request["order_type"] != "limit")
                or (purpose == "protective_stop" and request["order_type"] != "stop")):
            raise ValueError("Reducing dispatch order type disagrees with allocation purpose")
        if (allocation_state["unresolved_reasons"] or cancellation_state["unresolved_reasons"]
                or sell_state["unresolved_reasons"] or state["unresolved_reasons"]
                or account["unresolved_reasons"]):
            raise ValueError("Reducing dispatch evidence is unresolved")
        if entry_state["status"] != "reconciled" or sell_state["status"] != "reconciled":
            raise ValueError("Complete cumulative evidence is required before reducing dispatch")
        if current_writer["disarmed"] or current_writer["unresolved_reasons"]:
            raise ValueError("Writer is disarmed")
        if (current_writer["owner_id"], current_writer["epoch"]) != (
                request["owner_id"], request["writer_epoch"]):
            raise ValueError("Writer ownership or fencing epoch changed")
        allocation_request = allocation["request"]
        if (at >= utc(allocation_request["expires_at"])
                or at < utc(account["at"]) or at < utc(entry_state["as_of"])
                or at < utc(sell_state["as_of"]) or at < utc(state["as_of"])
                or (writer_events and at < utc(writer_events[-1]["at"]))):
            raise ValueError("Reducing dispatch authority is stale or moved backwards")
        if not at < expires or store._periods(request["at"]) != (account["session"], account["week"]):
            raise ValueError("Reducing dispatch requires current reviewed session authority")
        for label in ("quote_at", "fx_at"):
            observed = utc(allocation_request[label])
            if not timedelta(0) <= at - observed <= store.MAX_FRESHNESS:
                raise ValueError("Reducing dispatch " + label.replace("_at", "") + " is stale or future")
        for label, observed in (("entry snapshot", utc(entry_state["as_of"])),
                                ("reducing snapshot", utc(sell_state["as_of"]))):
            if not timedelta(0) <= at - observed <= store.MAX_FRESHNESS:
                raise ValueError("Reducing dispatch " + label + " is stale or future")
        entry_row = connection.execute("SELECT payload FROM intents WHERE intent_id=?",
                                       (allocation_request["entry_intent_id"],)).fetchone()
        if entry_row is None:
            raise ValueError("Reducing dispatch entry intent is missing")
        entry = store._record_payload(entry_row[0])
        if (purpose == "protective_stop"
                and money(request["stop_price_usd"]) < money(entry["proposal"]["stop_price_usd"])):
            raise ValueError("Protective stop price is below the planned stop")
        current_quantity = (sell_state["verified_quantity"] if sell_state["version"]
                            else account["position_quantity"])
        if current_quantity <= 0 or account["position_quantity"] != current_quantity:
            raise ValueError("Reducing dispatch requires verified current holdings")
        dispatch_by_allocation = {row["allocation_id"]: row for row in records.values()}
        orders = {row["client_order_id"]: row for row in sell_state["orders"]}
        committed = 0
        for row in allocation_records:
            if row["state"] != "reserved":
                continue
            operation = dispatch_by_allocation.get(row["allocation_id"])
            if operation is not None and operation["state"] in TERMINAL_STATES:
                continue
            order = orders.get(row["client_order_id"])
            committed += (row["quantity"] - order["cumulative_executed_quantity"]
                          if order is not None and order["state"] in ("working", "unknown")
                          else row["quantity"])
        target_operation = dispatch_by_allocation.get(allocation["allocation_id"])
        if committed > current_quantity or (target_operation is not None
                                             and target_operation["state"] in TERMINAL_STATES):
            raise ValueError("Reducing dispatch cumulative sell capacity is unavailable")
        command = _expected_command(request, allocation)
        record = {"schema": RECORD_SCHEMA, "operation_id": request["operation_id"],
                  "allocation_id": request["allocation_id"], "request": request,
                  "request_sha256": store.digest(request), "command": command,
                  "command_sha256": store.digest(command), "state": "submitting",
                  "adapter_result": None, "broker_order_id": None,
                  "marked_at": at.isoformat(), "resolved_at": None,
                  "owner_id": request["owner_id"], "writer_epoch": request["writer_epoch"],
                  "last_event_version": 0}
        reasons = sorted(set(state["unresolved_reasons"] + ["reducing_submission_pending"]))
        writer_event = _writer_transition(connection, request["operation_id"], at, reasons)
        state, record, _ = _append(connection, "marked", at, request, writer_event,
                                   state, record=record)
        records[record["operation_id"]] = record
        return _report(state, records, record=record)


def _record_result(path, operation_id, owner_id, writer_epoch, at, result):
    _adapter_result(result)
    with store.database(path, write=True) as connection:
        store._read_state(connection)
        state, records, incidents, _ = _read(connection)
        record = records.get(operation_id)
        if record is None or record["adapter_result"] is not None:
            raise ValueError("Reducing dispatch is not awaiting an adapter result")
        if (record["owner_id"], record["writer_epoch"]) != (owner_id, writer_epoch):
            raise ValueError("Reducing dispatch result fencing identity changed")
        result_at = utc(at)
        if result_at < utc(state["as_of"]):
            raise ValueError("Reducing dispatch result time moved backwards")
        record = _result_record(record, result, result_at)
        future = {**records, operation_id: record}
        reasons = _reasons(future, incidents)
        writer_event = _writer_transition(connection, operation_id, result_at, reasons)
        state, record, _ = _append(connection, "result", result_at, result,
                                   writer_event, state, record=record)
        future[operation_id] = record
        return _report(state, future, record=record)


def apply_evidence(connection, at, orders, evidence_id):
    """Correlate possible submissions with complete cumulative order evidence."""
    state, records, incidents, _ = _read(connection)
    at = at if hasattr(at, "isoformat") else utc(at)
    by_client = {row["client_order_id"]: row for row in orders}
    changed = []
    for operation_id in sorted(records):
        prior = records[operation_id]
        if prior["state"] not in ACTIVE_STATES | {"working"}:
            continue
        target = by_client.get(prior["command"]["client_order_id"])
        if target is None:
            continue
        if prior["state"] == "working" and target["state"] not in ("filled", "cancelled"):
            continue
        if prior["broker_order_id"] is not None and target["order_id"] != prior["broker_order_id"]:
            continue
        record = _evidence_record(prior, target, at)
        future = {**records, operation_id: record}
        reasons = _reasons(future, incidents)
        writer_event = _writer_transition(connection, operation_id, at, reasons)
        state, record, _ = _append(connection, "evidence", at,
                                   {"evidence_id": evidence_id, "order": target},
                                   writer_event, state, record=record)
        records[operation_id] = record
        changed.append(operation_id)
    return changed


def dispatch_synthetic(path, payload, outcome, adapter=None, result_at=None):
    if outcome not in SYNTHETIC_OUTCOMES:
        raise ValueError("Unsupported synthetic reducing dispatch outcome")
    adapter = adapter or SyntheticReducingAdapter()
    marked = mark(path, payload)
    if not marked["should_call_adapter"]:
        return marked
    try:
        result = adapter.submit(marked["operation"]["command"], outcome)
    except DispatchUncertain:
        result = {"outcome": "unknown", "reason": "lost_reducing_submission_response"}
    return _record_result(path, payload["operation_id"], payload["owner_id"],
                          payload["writer_epoch"], result_at or payload["at"], result)
