"""Atomic v4 synthetic reducing-order allocations; no dispatch capability."""
from copy import deepcopy
from datetime import timedelta
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
    "quote_at", "fx_at",
}


def _initialize_tables(connection, account_id, at):
    connection.execute("CREATE TABLE reducing_allocation_baseline "
                       "(id INTEGER PRIMARY KEY CHECK(id=1), payload TEXT NOT NULL)")
    connection.execute("INSERT INTO reducing_allocation_baseline "
                       "SELECT id,payload FROM account_state WHERE id=1")
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
    from . import order_sell_reconciliation
    order_sell_reconciliation._initialize_tables(connection, account_id, at)
    from . import order_cancellation
    order_cancellation._initialize_tables(connection, account_id, at)
    from . import order_reducing_dispatch
    order_reducing_dispatch._initialize_tables(connection, account_id, at)
    from . import order_controls
    order_controls._initialize_tables(connection)


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
        "exit_fee_allowance_usd", "committed_version", "evidence",
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
    required = {"incident_id", "kind", "at", "incoming", "matches", "committed_version",
                "request"}
    if (not isinstance(value, dict) or set(value) != required
            or value["kind"] != "allocation_identity_conflict"):
        raise ValueError("Invalid reducing allocation incident")
    store._identity(value["incident_id"], "allocation incident id")
    store._timestamp_string(value["at"], "allocation incident time")
    store._version(value["committed_version"], "allocation incident version")
    if (not isinstance(value["incoming"], dict)
            or not isinstance(value["request"], dict)
            or set(value["incoming"]) != {"allocation_id", "client_order_id", "request_sha256"}
            or not isinstance(value["matches"], list)
            or value["matches"] != sorted(set(value["matches"]))):
        raise ValueError("Invalid reducing allocation incident identities")
    for field in ("allocation_id", "client_order_id"):
        store._identity(value["incoming"][field], "incoming " + field.replace("_", " "))
        if value["request"].get(field) != value["incoming"][field]:
            raise ValueError("Allocation incident disagrees with retained request")
    if store.digest(value["request"]) != value["incoming"]["request_sha256"]:
        raise ValueError("Allocation incident request digest mismatch")
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


def _baseline(connection):
    row = connection.execute(
        "SELECT payload FROM reducing_allocation_baseline WHERE id=1").fetchone()
    if row is None:
        raise ValueError("Reducing allocation baseline missing")
    baseline = store._parse_state(row[0])
    if baseline["version"] != 0 or baseline["position_quantity"] != 0:
        raise ValueError("Invalid reducing allocation baseline")
    return baseline


def _proof(connection, request, retained_evidence=None):
    """Derive admission capacity from retained cumulative evidence."""
    baseline = _baseline(connection)
    _, reconciliation_events = order_reconciliation._read(connection)
    _, _, writer_events = order_writer._read_writer(connection)
    rv, wv = request["expected_reconciliation_version"], request["expected_writer_version"]
    if not 0 < rv <= len(reconciliation_events) or not 0 < wv <= len(writer_events):
        raise ValueError("Allocation evidence versions are unavailable")
    event, writer_event = reconciliation_events[rv - 1], writer_events[wv - 1]
    reconciled, writer = event["state"], writer_event["writer"]
    row = connection.execute(
        "SELECT payload_sha256,payload FROM reconciliation_inbox WHERE snapshot_id=?",
        (reconciled["last_snapshot_id"],)).fetchone()
    if row is None:
        raise ValueError("Allocation reconciliation input is missing")
    snapshot = order_reconciliation._snapshot(store.decode(row[1]))
    if (row[0] != store.digest(snapshot) or event["input_sha256"] != row[0]
            or event["kind"] != "snapshot_applied" or reconciled["status"] != "reconciled"
            or reconciled["unresolved_reasons"] or not all(snapshot["completeness"].values())
            or snapshot["expected_reconciliation_version"] != rv - 1
            or utc(event["at"]) != utc(snapshot["at"])
            or snapshot["account_id"] != baseline["account_id"]
            or request["account_id"] != baseline["account_id"]
            or request["expected_policy_sha256"] != store.digest(baseline["policy"])):
        raise ValueError("Allocation reconciliation input binding mismatch")
    row = connection.execute(
        "SELECT payload FROM reconciliation_adjustments WHERE reconciliation_id=?",
        (snapshot["reconciliation_id"],)).fetchone()
    if row is None:
        raise ValueError("Allocation entry adjustment evidence is missing")
    entry_adjustment = store._adjustment_payload(row[0])
    row = connection.execute("SELECT payload FROM intents WHERE intent_id=?",
                             (request["entry_intent_id"],)).fetchone()
    if row is None:
        raise ValueError("Allocation entry evidence missing")
    intent = store._record_payload(row[0])
    proposal = intent["proposal"]
    if (intent["state"] != "reserved" or proposal["instrument_id"] != request["instrument_id"]
            or proposal["account_id"] != baseline["account_id"]
            or proposal["side"] != "buy" or proposal["purpose"] != "entry"
            or intent["committed_version"] >= entry_adjustment["committed_version"]
            or entry_adjustment["intent_id"] != intent["intent_id"]
            or entry_adjustment["snapshot_id"] != snapshot["snapshot_id"]
            or entry_adjustment["reconciliation_id"] != snapshot["reconciliation_id"]
            or utc(entry_adjustment["at"]) != utc(snapshot["at"])):
        raise ValueError("Allocation entry/account evidence binding mismatch")
    submissions = {}
    for item in writer_events[:wv]:
        if item["submission"] is not None:
            submission = item["submission"]
            submissions[submission["operation_id"]] = submission
    prior = deepcopy(reconciliation_events[rv - 2]["state"] if rv > 1 else reconciled)
    if rv == 1:
        prior.update(executions=[], commissions=[], order_projection=None)
    prior["baseline_settled_cash_usd"] = baseline["settled_cash_usd"]
    reasons, submission, order, executions, commissions = order_reconciliation._validate_complete(
        prior, snapshot, submissions)
    if reasons or submission is None or order is None or submission["intent_id"] != intent["intent_id"]:
        raise ValueError("Allocation retained input does not prove entry capacity")
    if submission["command"] != order_writer._command(intent, submission["request"]):
        raise ValueError("Allocation submission disagrees with its entry intent")
    if (any(not utc(submission["marked_at"]) <= utc(item["at"]) <= utc(snapshot["at"])
            for item in executions.values())
            or any(not utc(executions[item["execution_id"]]["at"]) <= utc(item["at"]) <= utc(snapshot["at"])
                   for item in commissions.values())
            or {item["execution_id"] for item in commissions.values()} != set(executions)):
        raise ValueError("Allocation entry execution/fee evidence is incomplete or future")
    # A reconstructed projection must agree with the original cumulative input.
    projection = dict(intent_id=intent["intent_id"], client_order_id=order["client_order_id"],
                      broker_order_id=order["broker_order_id"], state=order["state"],
                      original_quantity=order["original_quantity"],
                      executed_quantity=order["cumulative_executed_quantity"])
    quantity = sum(item["quantity"] for item in executions.values())
    allowance = money(proposal["exit_fee_usd"])
    remaining = proposal["quantity"] - quantity if order["state"] == "working" else 0
    fees = sum((money(item["amount_usd"]) for item in commissions.values()), D("0"))
    cash_reserve = (D(remaining) * (money(proposal["limit_price_usd"])
                                  + money(proposal["slippage_usd_per_share"])) + allowance)
    if remaining:
        cash_reserve += max(money(proposal["entry_fee_usd"]) - fees, D("0"))
    if (quantity <= 0 or quantity != entry_adjustment["position_quantity"]
            or reconciled["order_projection"] != projection
            or reconciled["executions"] != [executions[key] for key in sorted(executions)]
            or reconciled["commissions"] != [commissions[key] for key in sorted(commissions)]
            or money(entry_adjustment["settled_cash_usd"]) != money(snapshot["currency_cash"]["USD"])
            or money(entry_adjustment["reserved_cash_usd"]) != cash_reserve
            or cash_reserve > money(entry_adjustment["settled_cash_usd"])):
        raise ValueError("Allocation capacity replay disagrees with retained input")
    row = connection.execute(
        "SELECT payload FROM reconciliation_adjustments WHERE committed_version=?",
        (request["expected_account_version"],)).fetchone()
    if row is None:
        raise ValueError("Allocation account evidence requires a fresh reconciliation")
    adjustment = store._adjustment_payload(row[0])
    from . import order_sell_reconciliation
    sell_event_rows = connection.execute(
        "SELECT sequence,event_id,kind,input_sha256,payload_sha256,payload "
        "FROM reducing_reconciliation_events ORDER BY sequence").fetchall()
    if retained_evidence is None:
        sell_version = len(sell_event_rows)
    else:
        sell_version = retained_evidence.get("reducing_reconciliation_version", 0)
    capacity_at = utc(snapshot["at"])
    sell_evidence = {}
    incurred_fee = D("0")
    if sell_version:
        if not 0 < sell_version <= len(sell_event_rows):
            raise ValueError("Allocation reducing evidence version is unavailable")
        sequence, event_id, kind, input_sha, payload_sha, raw = sell_event_rows[sell_version - 1]
        sell_event = store.decode(raw)
        if (sequence != sell_version or sell_event.get("event_id") != event_id
                or sell_event.get("kind") != kind or sell_event.get("input_sha256") != input_sha
                or store.digest(sell_event) != payload_sha):
            raise ValueError("Allocation reducing event evidence is invalid")
        sell_state = order_sell_reconciliation._state_payload(store.pack(sell_event["state"]))
        row = connection.execute(
            "SELECT payload_sha256,payload FROM reducing_reconciliation_inbox "
            "WHERE payload_sha256=?", (sell_event["input_sha256"],)).fetchone()
        if row is None:
            raise ValueError("Allocation reducing reconciliation input is missing")
        sell_snapshot = order_sell_reconciliation._snapshot(store.decode(row[1]))
        if (row[0] != store.digest(sell_snapshot)
                or sell_event["kind"] != "snapshot_applied"
                or sell_state["status"] != "reconciled" or sell_state["unresolved_reasons"]
                or not all(sell_snapshot["completeness"].values())
                or sell_state["account_version"] != request["expected_account_version"]
                or sell_state["entry_intent_id"] != request["entry_intent_id"]
                or sell_state["instrument_id"] != request["instrument_id"]
                or sell_event["account_adjustment_sha256"] != store.digest(adjustment)
                or adjustment["snapshot_id"] != sell_snapshot["snapshot_id"]
                or adjustment["reconciliation_id"] != sell_snapshot["reconciliation_id"]
                or adjustment["position_quantity"] != sell_state["verified_quantity"]
                or utc(sell_event["at"]) != utc(sell_snapshot["at"])):
            raise ValueError("Allocation reducing evidence binding mismatch")
        quantity = sell_state["verified_quantity"]
        incurred_fee = money(sell_state["incurred_exit_fees_usd"])
        capacity_at = utc(sell_snapshot["at"])
        sell_evidence = {
            "reducing_reconciliation_version": sell_version,
            "reducing_snapshot_sha256": store.digest(sell_snapshot),
            "reducing_reconciliation_event_sha256": store.digest(sell_event),
        }
    elif (adjustment != entry_adjustment
          or adjustment["committed_version"] != request["expected_account_version"]):
        raise ValueError("Allocation account evidence is newer than its reducing proof")
    if quantity <= 0 or adjustment["position_quantity"] != quantity:
        raise ValueError("Allocation current quantity proof is not a verified long position")
    decision = utc(request["decision_at"])
    if (writer["disarmed"] or writer["unresolved_reasons"]
            or (writer["owner_id"], writer["epoch"]) != (request["owner_id"], request["writer_epoch"])
            or utc(writer_event["at"]) < max(utc(event["at"]), capacity_at)
            or decision < utc(writer_event["at"])):
        raise ValueError("Allocation writer evidence is disarmed, changed or future")
    if store._periods(request["decision_at"]) != (baseline["session"], baseline["week"]):
        raise ValueError("Reducing allocation requires owner period review")
    bounds = store.session_bounds(baseline["session"])
    if bounds is None or not bounds[0] <= decision < bounds[1]:
        raise ValueError("Reducing allocation is outside the regular session")
    for label, at in (("snapshot", capacity_at.isoformat()), ("quote", request["quote_at"]),
                      ("fx", request["fx_at"])):
        if not timedelta(0) <= decision - utc(at) <= store.MAX_FRESHNESS:
            raise ValueError("Reducing allocation " + label + " is stale or future")
    evidence = {"snapshot_id": snapshot["snapshot_id"], "snapshot_sha256": store.digest(snapshot),
                "reconciliation_event_sha256": store.digest(event),
                "account_adjustment_sha256": store.digest(adjustment),
                "writer_event_sha256": store.digest(writer_event),
                "entry_intent_sha256": store.digest(intent), **sell_evidence}
    return quantity, allowance, incurred_fee, evidence


def _read(connection):
    if connection.execute("PRAGMA user_version").fetchone()[0] != store.REDUCING_DATABASE_VERSION:
        raise ValueError("Reducing allocations require a fresh v4 order database")
    row = connection.execute("SELECT payload FROM reducing_allocation_state WHERE id=1").fetchone()
    if row is None:
        raise ValueError("Reducing allocation state missing; explicit recovery required")
    state = _state_payload(row[0])
    records = []
    for allocation_id, client_order_id, request_sha, version, raw in connection.execute(
            "SELECT allocation_id,client_order_id,request_sha256,committed_version,payload "
            "FROM reducing_allocations ORDER BY committed_version"):
        record = _record_payload(raw)
        if (allocation_id, client_order_id, request_sha, version) != (
                record["allocation_id"], record["client_order_id"], record["request_sha256"],
                record["committed_version"]):
            raise ValueError("Reducing allocation identity columns disagree with payload")
        records.append(record)
    incidents = []
    for incident_id, version, raw in connection.execute(
            "SELECT incident_id,committed_version,payload FROM reducing_allocation_incidents ORDER BY committed_version"):
        incident = _incident_payload(raw)
        if (incident_id, version) != (incident["incident_id"], incident["committed_version"]):
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
    from . import order_reducing_dispatch
    _, dispatch_records, _, _ = order_reducing_dispatch._read(connection)

    def quantity_released_before(allocation_id, at):
        return any(row["allocation_id"] == allocation_id
                   and row["state"] in ("rejected", "cancelled", "filled")
                   and row["resolved_at"] is not None
                   and utc(row["resolved_at"]) <= at
                   for row in dispatch_records.values())

    def fee_released_before(allocation_id, at):
        return any(row["allocation_id"] == allocation_id
                   and row["state"] in ("rejected", "cancelled", "filled")
                   and row["resolved_at"] is not None
                   and utc(row["resolved_at"]) <= at
                   for row in dispatch_records.values())
    episode = None
    baseline = _baseline(connection)
    account = store._parse_state(connection.execute(
        "SELECT payload FROM account_state WHERE id=1").fetchone()[0])
    if (state["account_id"] != baseline["account_id"]
            or any(account[key] != baseline[key] for key in (
                "account_id", "environment", "policy", "session", "week", "session_start", "week_start"))):
        raise ValueError("Allocation baseline account mismatch")
    last_at = utc(baseline["at"])
    prior_records = []
    incident_seen = False
    for item in combined:
        at = utc(item["at"] if "incident_id" in item else item["request"]["decision_at"])
        if at < last_at:
            raise ValueError("Reducing allocation event time moved backwards")
        last_at = at
        if "incident_id" in item:
            incoming = item["incoming"]
            matched = [row for row in prior_records
                       if row["allocation_id"] == incoming["allocation_id"]
                       or row["client_order_id"] == incoming["client_order_id"]]
            matches = sorted(row["allocation_id"] for row in matched)
            if not matches or matches != item["matches"]:
                raise ValueError("Allocation incident does not match prior identities")
            if (at < utc(item["request"]["decision_at"])
                    or (len(matched) == 1 and all(matched[0][key] == incoming[key]
                                                for key in incoming))):
                raise ValueError("Invalid allocation conflict transition")
            incident_seen = True
        else:
            if incident_seen or item["request"]["expected_allocation_version"] != item["committed_version"] - 1:
                raise ValueError("Allocation transition is unresolved or has a stale version")
            if prior_records and any(item["request"][field] < prior_records[-1]["request"][field]
                                     for field in ("expected_account_version",
                                                   "expected_reconciliation_version",
                                                   "expected_writer_version")):
                raise ValueError("Allocation evidence versions moved backwards")
            prior_records.append(item)
    capacity_records = []
    for record in records:
        request = record["request"]
        decision_at = utc(request["decision_at"])
        reserved_quantity = sum(
            row["quantity"] for row in capacity_records
            if row["state"] == "reserved"
            and not quantity_released_before(row["allocation_id"], decision_at))
        reserved_fee = sum(
            (money(row["fee_bound_usd"]) for row in capacity_records
             if row["state"] == "reserved"
             and not fee_released_before(row["allocation_id"], decision_at)), D("0"))
        if connection.execute("SELECT 1 FROM intents WHERE intent_id=? OR client_order_id=?",
                              (request["allocation_id"], request["client_order_id"])).fetchone():
            raise ValueError("Allocation identity overlaps an entry intent")
        if request["account_id"] != state["account_id"]:
            raise ValueError("Reducing allocation record account mismatch")
        current_episode = (request["entry_intent_id"], request["instrument_id"],
                           money(record["exit_fee_allowance_usd"]))
        if episode is None:
            episode = current_episode
        elif current_episode != episode:
            raise ValueError("Reducing allocation audit crosses entry episodes")
        quantity, allowance, incurred_fee, evidence = _proof(
            connection, request, record["evidence"])
        reserved_fee += incurred_fee
        if (record["verified_quantity"] != quantity
                or money(record["exit_fee_allowance_usd"]) != allowance
                or record["evidence"] != evidence):
            raise ValueError("Reducing allocation capacity replay evidence mismatch")
        reasons = []
        if record["quantity"] > quantity - reserved_quantity:
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
        capacity_records.append(record)
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
                      else combined[-1]["request"]["decision_at"]) if combined else baseline["at"]
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
        "capacity_scope": "at_last_allocation_decision", "dispatch_authorized": False,
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
    for field in ("quote_at", "fx_at"):
        store._timestamp_string(raw[field], field)
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
                # Receipt ordering is distinct from source decision time. Even a
                # stale conflicting command must latch, without moving time back.
                incident_at = max(shallow_at, utc(state["as_of"]), utc(account["at"]))
                version = state["version"] + 1
                incident = dict(incident_key, incident_id=incident_id,
                                at=incident_at.isoformat(), committed_version=version,
                                request=deepcopy(raw))
                connection.execute(
                    "INSERT INTO reducing_allocation_incidents VALUES (?, ?, ?)",
                    (incident_id, version, store.pack(incident)))
                connection.execute(
                    "INSERT INTO reducing_allocation_audit VALUES (?, 'incident', ?, ?)",
                    (version, incident_id, store.digest(incident)))
                state.update(version=version, as_of=incident_at.isoformat(),
                             unresolved_reasons=["allocation_identity_conflict"])
                _write_state(connection, state)
            result = _report(state, records)
            result.update(outcome="identity_conflict", reasons=["allocation_identity_conflict"],
                          duplicate=existing is not None)
            return result

        from . import order_controls
        if order_controls._blocks(connection, management=True):
            raise ValueError("Protection control identity is unresolved")
        decision, fee = _validated_request(raw)
        if connection.execute("SELECT 1 FROM intents WHERE intent_id=? OR client_order_id=?",
                              (allocation_id, client_order_id)).fetchone():
            raise ValueError("Reducing identities collide with an entry intent")
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
                or projection["executed_quantity"] < account["position_quantity"]
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
        if state["entry_intent_id"] is not None and (
                state["entry_intent_id"] != raw["entry_intent_id"]
                or state["instrument_id"] != raw["instrument_id"]
                or money(state["exit_fee_allowance_usd"]) != allowance):
            raise ValueError("Reducing allocation entry episode changed")

        quantity, proved_allowance, incurred_fee, evidence = _proof(connection, raw)
        if quantity != account["position_quantity"] or proved_allowance != allowance:
            raise ValueError("Reducing allocation current evidence mismatch")
        if money(account["reserved_cash_usd"]) < max(allowance - incurred_fee, D("0")):
            raise ValueError("Remaining exit-fee allowance is not reserved in settled cash")

        from . import order_reducing_dispatch
        _, dispatch_records, _, _ = order_reducing_dispatch._read(connection)
        quantity_released = {row["allocation_id"] for row in dispatch_records.values()
                             if row["state"] in ("rejected", "cancelled", "filled")
                             and row["resolved_at"] is not None
                             and utc(row["resolved_at"]) <= decision}
        fee_released = {row["allocation_id"] for row in dispatch_records.values()
                        if row["state"] in ("rejected", "cancelled", "filled")
                        and row["resolved_at"] is not None
                        and utc(row["resolved_at"]) <= decision}
        active_quantity = sum(row["quantity"] for row in records
                              if row["state"] == "reserved"
                              and row["allocation_id"] not in quantity_released)
        active_fee = incurred_fee + sum(
            (money(row["fee_bound_usd"]) for row in records
             if row["state"] == "reserved" and row["allocation_id"] not in fee_released), D("0"))
        available_quantity = account["position_quantity"] - active_quantity
        if available_quantity < 0:
            raise ValueError("Current position is below already reserved reducing quantity")
        available_fee = allowance - active_fee
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
            "evidence": evidence,
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
            state["reserved_quantity"] = active_quantity + raw["quantity"]
            state["reserved_fee_usd"] = str(active_fee + fee)
        else:
            state["reserved_quantity"] = active_quantity
            state["reserved_fee_usd"] = str(active_fee)
        _write_state(connection, state)
        records.append(record)
        result = _report(state, records)
        result.update(outcome=record["state"], reasons=reasons,
                      duplicate=False, allocation=record)
        return result
