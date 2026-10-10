"""Durable v4 protection controls. Owner recovery is test-injected only.

There is deliberately no production owner authenticator or recovery CLI. The
private recovery fixture is restricted to the synthetic store and is not an
owner-authentication implementation.
"""
from copy import deepcopy

from .ledger import utc
from . import order_store as store

SCHEMA = "protection-control-request-v1"
SOURCES = {
    "account": "audit", "entry": "reconciliation_events",
    "sell": "reducing_reconciliation_events", "allocation": "reducing_allocation_audit",
    "writer": "writer_events", "cancellation": "cancellation_events",
    "dispatch": "reducing_dispatch_events",
}
FIELDS = {"schema", "control_id", "account_id", "environment", "at", "action",
          "incident_id", "expected_version", "expected_sources"}
ACTIONS = {"pause", "hold", "cancel_entry_remainder", "flatten", "resume", "resolve"}


def _baseline(connection):
    return store._parse_state(connection.execute(
        "SELECT payload FROM reducing_allocation_baseline WHERE id=1").fetchone()[0])


def _sources(connection):
    result = {}
    for name, table in SOURCES.items():
        row = connection.execute(
            f"SELECT sequence,payload_sha256 FROM {table} ORDER BY sequence DESC LIMIT 1").fetchone()
        result[name] = list(row) if row else [0, None]
    return result


def _events(connection, table, version):
    return [store.decode(row[0]) for row in connection.execute(
        f"SELECT payload FROM {table} WHERE sequence<=? ORDER BY sequence", (version,))]


def _validate_sources(sources):
    if not isinstance(sources, dict) or set(sources) != set(SOURCES):
        raise ValueError("Invalid protection source bindings")
    for ref in sources.values():
        if not isinstance(ref, list) or len(ref) != 2:
            raise ValueError("Invalid protection source reference")
        store._version(ref[0], "protection source version")
        if ((ref[0] == 0 and ref[1] is not None) or
                (ref[0] and (not isinstance(ref[1], str) or len(ref[1]) != 64
                            or any(char not in "0123456789abcdef" for char in ref[1])))):
            raise ValueError("Invalid protection source digest")


def _facts(connection, sources):
    """Reconstruct facts using bounded, retained journal prefixes, never projections."""
    _validate_sources(sources)
    for name, table in SOURCES.items():
        ref = sources[name]
        row = connection.execute(
            f"SELECT payload_sha256 FROM {table} WHERE sequence=?", (ref[0],)).fetchone()
        if (ref[0] == 0 and ref[1] is not None) or (ref[0] and (row is None or row[0] != ref[1])):
            raise ValueError("Protection source digest mismatch")
    baseline = _baseline(connection)
    account_version = sources["account"][0]
    adjustments = [store._adjustment_payload(row[0]) for row in connection.execute(
        "SELECT payload FROM reconciliation_adjustments WHERE committed_version<=? "
        "ORDER BY committed_version", (account_version,))]
    account = adjustments[-1] if adjustments else baseline
    entry_events = _events(connection, SOURCES["entry"], sources["entry"][0])
    sell_events = _events(connection, SOURCES["sell"], sources["sell"][0])
    entry = entry_events[-1]["state"] if entry_events else None
    sell = sell_events[-1]["state"] if sell_events else None
    dispatch_events = _events(connection, SOURCES["dispatch"], sources["dispatch"][0])
    cancel_events = _events(connection, SOURCES["cancellation"], sources["cancellation"][0])
    writer_events = _events(connection, SOURCES["writer"], sources["writer"][0])
    dispatched, cancelled, submitted = {}, {}, {}
    for events, target, field, key in (
            (dispatch_events, dispatched, "record", "allocation_id"),
            (cancel_events, cancelled, "record", "target_client_order_id"),
            (writer_events, submitted, "submission", "intent_id")):
        for event in events:
            record = event[field]
            if record is not None:
                identity = record.get(key, record.get("request", {}).get(key))
                target[identity] = record
    allocations = [store.decode(row[0]) for row in connection.execute(
        "SELECT payload FROM reducing_allocations WHERE committed_version<=? ORDER BY committed_version",
        (sources["allocation"][0],))]
    intents = [store.decode(row[0]) for row in connection.execute(
        "SELECT payload FROM intents WHERE committed_version<=?", (account_version,))]
    releases = [store.decode(row[0]) for row in connection.execute(
        "SELECT payload FROM reservation_releases WHERE committed_version<=?", (account_version,))]
    released = {row["intent_id"] for row in releases}
    entry_order = entry["order_projection"] if entry else None
    orders = {row["client_order_id"]: row for row in sell["orders"]} if sell else {}
    possible_entry = False
    for intent in intents:
        if intent["state"] != "reserved" or intent["intent_id"] in released:
            continue
        order = orders.get(intent["client_order_id"])
        if order is None and entry_order and entry_order["intent_id"] == intent["intent_id"]:
            order = entry_order
        submission = submitted.get(intent["intent_id"])
        if order is None:
            possible_entry |= submission is None or submission["state"] not in ("rejected", "cancelled")
        else:
            possible_entry |= order["state"] not in ("filled", "cancelled")
    quantity = account["position_quantity"]
    uncertain = bool((entry and entry["status"] != "reconciled") or
                     (sell and sell["status"] != "reconciled"))
    covered, committed = 0, 0
    stop_pending = stop_unknown = stop_rejected = False
    for allocation in allocations:
        if allocation["state"] != "reserved":
            continue
        operation = dispatched.get(allocation["allocation_id"])
        order = orders.get(allocation["client_order_id"])
        terminal = operation and operation["state"] in ("rejected", "filled", "cancelled")
        remainder = (0 if terminal else allocation["quantity"] -
                     (order["cumulative_executed_quantity"] if order else 0))
        committed += remainder
        if allocation["request"]["purpose"] != "protective_stop":
            continue
        cancel = cancelled.get(allocation["client_order_id"])
        cancel_pending = cancel and cancel["state"] in ("cancel_pending", "accepted", "unknown")
        state = operation["state"] if operation else "queued"
        stop_rejected |= state == "rejected"
        stop_unknown |= bool(remainder and (state in ("unknown", "conflict") or cancel_pending))
        stop_pending |= bool(remainder and state in ("queued", "submitting", "acknowledged"))
        if remainder and state == "working" and order and order["state"] == "working" and not cancel_pending:
            covered += remainder
    uncertain |= committed > quantity or covered > quantity
    exposure = ("unresolved" if uncertain or (quantity == 0 and (possible_entry or committed))
                else "verified_long" if quantity else "verified_flat")
    protection = ("not_required" if exposure == "verified_flat" else
                  "unknown" if exposure == "unresolved" or stop_unknown else
                  "active" if covered == quantity else "partial" if covered else
                  "pending" if stop_pending else "rejected" if stop_rejected else "missing")
    causes = set()
    uncertain_submission = any(row["state"] == "unknown" for row in submitted.values())
    if protection in ("missing", "partial", "unknown", "rejected") and (quantity or uncertain or uncertain_submission):
        causes.add("protection_" + protection)
    if stop_rejected and quantity and protection != "active":
        causes.add("protective_stop_rejected")
    if sell and sell["unresolved_reasons"]:
        causes.update("reconciliation:" + reason for reason in sell["unresolved_reasons"])
    evidence = sell_events[-1] if sell_events else entry_events[-1] if entry_events else None
    proof_at = evidence["at"] if evidence else baseline["at"]
    # An initial zero balance alone is not a new reconciliation for recovery.
    complete = bool(evidence and evidence["kind"] == "snapshot_applied" and not uncertain
                    and adjustments and adjustments[-1]["committed_version"] == account_version
                    and (not writer_events or not writer_events[-1]["writer"]["unresolved_reasons"])
                    and (not sell or sell["account_version"] == account_version))
    times = [baseline["at"], account["at"]]
    times.extend(row["proposal"]["decision_at"] for row in intents)
    times.extend(row["at"] for row in releases)
    times.extend(row["request"]["decision_at"] for row in allocations)
    times.extend(store.decode(row[0])["at"] for row in connection.execute(
        "SELECT payload FROM reducing_allocation_incidents WHERE committed_version<=?",
        (sources["allocation"][0],)))
    times.extend(event["at"] for event in entry_events + sell_events + writer_events + dispatch_events + cancel_events)
    return {"exposure": exposure, "protection": protection, "quantity": quantity,
            "covered_quantity": covered if not uncertain else 0,
            "committed_sell_quantity": committed, "possible_entry": possible_entry,
            "causes": sorted(causes), "complete": complete, "proof_at": proof_at,
            "as_of": max(map(utc, times)).isoformat()}


def _initial(connection):
    baseline = _baseline(connection)
    return {"schema": "protection-control-state-v1", "version": 0,
            "account_id": baseline["account_id"], "environment": "synthetic",
            "as_of": baseline["at"], "operator_paused": False, "desired_action": "hold",
            "incidents": [], "sources": {name: [0, None] for name in SOURCES},
            "live_trading_enabled": False}


def _initialize_tables(connection):
    connection.execute("CREATE TABLE protection_control_state (id INTEGER PRIMARY KEY CHECK(id=1), payload TEXT NOT NULL)")
    connection.execute("CREATE TABLE protection_control_events (sequence INTEGER PRIMARY KEY, payload_sha256 TEXT NOT NULL, payload TEXT NOT NULL)")
    connection.execute("INSERT INTO protection_control_state VALUES (1, ?)", (store.pack(_initial(connection)),))


def _request(raw):
    value = deepcopy(raw)
    if not isinstance(value, dict) or set(value) != FIELDS or value["schema"] != SCHEMA:
        raise ValueError("Protection control fields do not match the contract")
    for field in ("control_id", "account_id"):
        store._identity(value[field], field)
    store._timestamp_string(value["at"], "control time")
    store._version(value["expected_version"], "control version")
    _validate_sources(value["expected_sources"])
    if value["environment"] != "synthetic" or value["action"] not in ACTIONS:
        raise ValueError("Unsupported protection control")
    if value["action"] == "resolve":
        store._identity(value["incident_id"], "incident id")
    elif value["incident_id"] is not None:
        raise ValueError("Only a resolution may reference an incident")
    return value


def _transition(connection, prior, event, commands):
    state = deepcopy(prior)
    sources = event["sources"]
    facts = _facts(connection, sources)
    if any(sources[key][0] < prior["sources"][key][0] for key in SOURCES):
        raise ValueError("Protection sources moved backwards")
    at = utc(event["at"])
    if at < max(utc(prior["as_of"]), utc(facts["as_of"])):
        raise ValueError("Protection control time moved backwards")
    request, auth = event["request"], event["authorization"]
    kind = event["kind"]
    if kind == "observation":
        if request is not None or auth is not None or sources == prior["sources"]:
            raise ValueError("Invalid protection observation")
    else:
        request = _request(request)
        if request["account_id"] != state["account_id"]:
            raise ValueError("Protection account mismatch")
        previous = commands.get(request["control_id"])
        if kind == "conflict":
            if previous is None or previous == request or auth is not None:
                raise ValueError("Invalid protection identity conflict")
            causes = ["control_identity_conflict"]
        elif kind == "command":
            if previous is not None or request["expected_version"] != prior["version"] or request["expected_sources"] != sources:
                raise ValueError("Protection control version or evidence changed")
            if utc(request["at"]) != at:
                raise ValueError("Protection request time mismatch")
            action = request["action"]
            if action in ("resolve", "resume"):
                if (not isinstance(auth, dict) or set(auth) != {"scope", "owner_event_id", "request_sha256"}
                        or auth["scope"] != "synthetic_test_only"
                        or auth["request_sha256"] != store.digest(request)):
                    raise ValueError("Separately authorized owner control required")
                store._identity(auth["owner_event_id"], "owner control event")
                if not facts["complete"] or not store.timedelta(0) <= at - utc(facts["proof_at"]) <= store.MAX_FRESHNESS:
                    raise ValueError("Owner recovery requires complete fresh reconciliation")
                if facts["exposure"] == "unresolved" or facts["protection"] not in ("active", "not_required"):
                    raise ValueError("Owner recovery requires resolved exposure and protection")
                # A proof must follow the affected control/incident, not merely be fresh.
                if action == "resume":
                    pause_events = [row for row in commands.values() if row["action"] == "pause"]
                    if not state["operator_paused"] or any(row["status"] == "open" for row in state["incidents"]):
                        raise ValueError("Resolve incidents before resuming an operator pause")
                    since = max(utc(row["at"]) for row in pause_events)
                    state["operator_paused"] = False
                else:
                    incident = next((row for row in state["incidents"] if row["incident_id"] == request["incident_id"]), None)
                    if incident is None or incident["status"] != "open":
                        raise ValueError("Owner recovery incident is not open")
                    from .order_sell_reconciliation import DURABLE_REASONS
                    unsupported = {"reconciliation:" + reason for reason in DURABLE_REASONS}
                    if incident["kind"] in unsupported | {"control_identity_conflict"}:
                        raise ValueError("Unsupported incident repair remains blocked")
                    if incident["kind"] in facts["causes"]:
                        raise ValueError("Incident cause remains unresolved")
                    since = utc(incident["opened_at"])
                    incident.update(status="resolved", resolution_id=request["control_id"])
                if utc(facts["proof_at"]) <= since:
                    raise ValueError("Owner recovery needs a new reconciliation after the control")
            elif auth is not None:
                raise ValueError("Unexpected owner authorization")
            elif action == "pause":
                state["operator_paused"] = True
            else:
                if action == "hold" and state["desired_action"] != "hold":
                    raise ValueError("Relaxing a durable objective requires a separately reviewed owner policy")
                if state["desired_action"] == "flatten" and action != "flatten":
                    raise ValueError("Flatten objective cannot be weakened")
                state["desired_action"] = action
            commands[request["control_id"]] = request
            causes = []
        else:
            raise ValueError("Invalid protection event kind")
        for cause in causes:
            _incident(state, cause, at, sources)
    for cause in facts["causes"]:
        _incident(state, cause, at, sources)
    if "protective_stop_rejected" in facts["causes"]:
        state["desired_action"] = "flatten"
    state.update(version=prior["version"] + 1, as_of=at.isoformat(), sources=deepcopy(sources))
    return state


def _incident(state, kind, at, sources):
    if any(row["kind"] == kind and row["status"] == "open" for row in state["incidents"]):
        return
    identity = {"kind": kind, "opened_version": state["version"] + 1, "sources": sources}
    state["incidents"].append({"incident_id": "protection-" + store.digest(identity)[:32],
                               "kind": kind, "opened_at": at.isoformat(),
                               "opened_sources": deepcopy(sources), "status": "open",
                               "resolution_id": None})


def _read(connection, *, check_sources=False):
    if connection.execute("PRAGMA user_version").fetchone()[0] != store.REDUCING_DATABASE_VERSION:
        raise ValueError("Protection controls require a fresh v4 order database")
    row = connection.execute("SELECT payload FROM protection_control_state WHERE id=1").fetchone()
    if row is None:
        raise ValueError("Protection control state missing; fresh initialization required")
    state, events, commands = _initial(connection), [], {}
    auth_ids = set()
    for expected, (sequence, sha, raw) in enumerate(connection.execute(
            "SELECT sequence,payload_sha256,payload FROM protection_control_events ORDER BY sequence"), 1):
        event = store.decode(raw)
        if (sequence != expected or not isinstance(event, dict) or set(event) != {
                "kind", "at", "sources", "request", "authorization", "prior_sha256", "state"}
                or store.digest(event) != sha or event["prior_sha256"] != store.digest(state)):
            raise ValueError("Invalid protection control event")
        if event["authorization"] is not None:
            if not isinstance(event["authorization"], dict):
                raise ValueError("Invalid owner control event")
            identity = store._identity(event["authorization"].get("owner_event_id"), "owner control event")
            if identity in auth_ids:
                raise ValueError("Owner control event reused")
            auth_ids.add(identity)
        state = _transition(connection, state, event, commands)
        if state != event["state"]:
            raise ValueError("Protection control replay mismatch")
        events.append(event)
    if state != store.decode(row[0]):
        raise ValueError("Protection control projection mismatch")
    if check_sources and state["sources"] != _sources(connection):
        raise ValueError("Protection observation is missing for committed evidence")
    return state, events


def _append(connection, state, events, kind, at, sources, request=None, authorization=None):
    event = {"kind": kind, "at": at, "sources": deepcopy(sources), "request": request,
             "authorization": authorization, "prior_sha256": store.digest(state)}
    commands = {row["request"]["control_id"]: row["request"] for row in events if row["kind"] == "command"}
    state = _transition(connection, state, event, commands)
    event["state"] = state
    connection.execute("INSERT INTO protection_control_events VALUES (?, ?, ?)",
                       (state["version"], store.digest(event), store.pack(event)))
    connection.execute("UPDATE protection_control_state SET payload=? WHERE id=1", (store.pack(state),))
    return state


def _sync(connection):
    state, events = _read(connection)
    sources = _sources(connection)
    if sources != state["sources"]:
        at = max(utc(state["as_of"]), utc(_facts(connection, sources)["as_of"])).isoformat()
        _append(connection, state, events, "observation", at, sources)


def _blocks(connection, *, management=False):
    state, _ = _read(connection)
    if management:
        return [row["incident_id"] for row in state["incidents"]
                if row["status"] == "open" and row["kind"] == "control_identity_conflict"]
    reasons = ["protection_incident:" + row["incident_id"] for row in state["incidents"] if row["status"] == "open"]
    if state["operator_paused"]:
        reasons.append("operator_paused")
    if state["desired_action"] != "hold":
        reasons.append("desired_action:" + state["desired_action"])
    return sorted(reasons)


def _report(connection, state, duplicate=False, outcome="recorded"):
    facts = _facts(connection, _sources(connection))
    return {**deepcopy(state), "facts": facts, "duplicate": duplicate, "outcome": outcome,
            "entry_blocked_reasons": _blocks(connection), "dispatch_authorized": False,
            "owner_recovery_available": False,
            "entry_cancellation_required": state["desired_action"] != "hold" and facts["possible_entry"]}


def _apply(path, raw, authorization=None):
    request = _request(raw)
    with store.database(path, write=True) as connection:
        store._read_state(connection)
        state, events = _read(connection)
        prior = next((event for event in events if event["request"] == request), None)
        if prior is not None:
            return _report(connection, state, True, "identity_conflict" if prior["kind"] == "conflict" else "recorded")
        reused = any(event["request"] and event["request"]["control_id"] == request["control_id"] for event in events)
        sources = _sources(connection)
        if reused:
            at = max(utc(request["at"]), utc(state["as_of"]), utc(_facts(connection, sources)["as_of"])).isoformat()
            state = _append(connection, state, events, "conflict", at, sources, request)
            return _report(connection, state, outcome="identity_conflict")
        if authorization and any(event["authorization"] and event["authorization"]["owner_event_id"] == authorization["owner_event_id"] for event in events):
            raise ValueError("Owner control event reused")
        state = _append(connection, state, events, "command", request["at"], sources, request, authorization)
        return _report(connection, state)


def apply(path, raw):
    """Restrictive operator commands only. A payload cannot assert owner authority."""
    return _apply(path, raw)


def _recover_for_test(path, raw, *, owner_event_id):
    """Synthetic test injection, NOT a production owner-authentication boundary."""
    if raw.get("action") not in ("resolve", "resume"):
        raise ValueError("Test owner control must be a recovery")
    return _apply(path, raw, {"scope": "synthetic_test_only", "owner_event_id": owner_event_id,
                             "request_sha256": store.digest(raw)})


def status(path):
    with store.database(path) as connection:
        store._read_state(connection)
        state, _ = _read(connection)
        return _report(connection, state)


def history(path):
    with store.database(path) as connection:
        store._read_state(connection)
        return _read(connection)[1]
