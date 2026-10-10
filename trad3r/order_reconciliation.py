"""Durable cumulative reconciliation for the synthetic single-order boundary."""
from copy import deepcopy
from decimal import Decimal as D

from .data import decode
from .ledger import utc
from .risk import assess, money
from . import order_store as store
from . import order_writer as writer


STATE_SCHEMA = "order-reconciliation-state-v1"
SNAPSHOT_SCHEMA = "synthetic-reconciliation-snapshot-v1"
INVALIDATION_SCHEMA = "order-reconciliation-invalidation-v1"
EVENT_SCHEMA = "order-reconciliation-event-v1"
WRITER_REQUEST_SCHEMA = "writer-reconciliation-v1"
MODE = "synthetic_cumulative_reconciliation_only"

STATE_FIELDS = {
    "schema", "version", "account_id", "environment", "baseline_settled_cash_usd",
    "as_of", "status", "last_snapshot_id", "unresolved_reasons", "executions",
    "commissions", "order_projection", "live_trading_enabled",
}
SNAPSHOT_FIELDS = {
    "schema", "snapshot_id", "reconciliation_id", "account_id", "environment", "at",
    "expected_reconciliation_version", "completeness", "orders", "executions",
    "commissions", "currency_cash", "positions", "unsettled_usd",
    "pending_settlements", "mark",
}
COMPLETENESS_FIELDS = {
    "orders", "executions", "positions", "currency_cash", "commissions", "settlement",
}
ORDER_FIELDS = {
    "client_order_id", "broker_order_id", "state", "original_quantity",
    "cumulative_executed_quantity",
}
EXECUTION_FIELDS = {
    "execution_id", "client_order_id", "broker_order_id", "instrument_id", "symbol",
    "currency", "side", "quantity", "price_usd", "at",
}
COMMISSION_FIELDS = {"commission_id", "execution_id", "currency", "amount_usd", "at", "revision"}
POSITION_FIELDS = {"instrument_id", "symbol", "currency", "quantity"}
INVALIDATION_FIELDS = {"schema", "event_id", "at", "reason"}
INVALIDATION_REASONS = {"startup", "disconnect"}
ORDER_STATES = {"working", "filled", "rejected", "cancelled"}
EVENT_KINDS = {"invalidated", "snapshot_applied", "snapshot_unresolved", "incident"}
DURABLE_REASONS = {
    "snapshot_identity_conflict", "reconciliation_identity_conflict",
    "invalidation_identity_conflict", "execution_history_changed",
    "commission_history_changed", "commission_execution_missing",
    "execution_identity_conflict", "commission_identity_conflict",
    "multiple_submissions_unsupported", "external_activity_unknown",
    "client_order_mismatch", "original_quantity_mismatch",
    "broker_order_identity_changed", "external_execution_unknown",
    "execution_order_mismatch", "execution_overfill", "position_identity_mismatch",
    "order_state_regression", "reservation_owner_conflict",
}
TRANSIENT_REASONS = {
    "reconciliation_required", "snapshot_incomplete", "order_outcome_unknown",
    "broker_order_id_missing", "order_execution_quantity_mismatch",
    "filled_quantity_mismatch", "rejected_order_has_execution",
    "working_quantity_mismatch", "cancelled_quantity_mismatch",
    "position_quantity_mismatch", "currency_cash_mismatch", "settlement_mismatch",
}


def _state_payload(raw):
    value = decode(raw) if not isinstance(raw, dict) else deepcopy(raw)
    if not isinstance(value, dict) or set(value) != STATE_FIELDS or value["schema"] != STATE_SCHEMA:
        raise ValueError("Invalid stored reconciliation state")
    store._version(value["version"], "reconciliation version")
    store._identity(value["account_id"], "reconciliation account id")
    if value["environment"] != "synthetic" or value["live_trading_enabled"] is not False:
        raise ValueError("Reconciliation is not synthetic and disarmed")
    store._decimal_string(value["baseline_settled_cash_usd"], "baseline settled cash")
    store._timestamp_string(value["as_of"], "reconciliation time")
    if value["status"] not in ("reconciled", "required", "unresolved"):
        raise ValueError("Invalid reconciliation status")
    if value["last_snapshot_id"] is not None:
        store._identity(value["last_snapshot_id"], "last snapshot id")
    if (not isinstance(value["unresolved_reasons"], list)
            or value["unresolved_reasons"] != sorted(set(value["unresolved_reasons"]))):
        raise ValueError("Invalid reconciliation reasons")
    if ((value["status"] == "reconciled") != (not value["unresolved_reasons"])):
        raise ValueError("Reconciliation status disagrees with unresolved reasons")
    if not isinstance(value["executions"], list) or not isinstance(value["commissions"], list):
        raise ValueError("Invalid cumulative reconciliation evidence")
    for row in value["executions"]:
        _execution(row)
    for row in value["commissions"]:
        _commission(row)
    if len({row["execution_id"] for row in value["executions"]}) != len(value["executions"]):
        raise ValueError("Stored reconciliation executions are not unique")
    if len({row["commission_id"] for row in value["commissions"]}) != len(value["commissions"]):
        raise ValueError("Stored reconciliation commissions are not unique")
    projection = value["order_projection"]
    if projection is not None:
        required = {"intent_id", "client_order_id", "broker_order_id", "state",
                    "original_quantity", "executed_quantity"}
        if not isinstance(projection, dict) or set(projection) != required:
            raise ValueError("Invalid reconciliation order projection")
        store._identity(projection["intent_id"], "projection intent id")
        store._identity(projection["client_order_id"], "projection client order id")
        if projection["broker_order_id"] is not None:
            store._identity(projection["broker_order_id"], "projection broker order id")
        if projection["state"] not in ORDER_STATES:
            raise ValueError("Invalid reconciliation order state")
        for key in ("original_quantity", "executed_quantity"):
            if type(projection[key]) is not int or projection[key] < 0:
                raise ValueError("Invalid reconciliation order quantity")
        if (projection["original_quantity"] <= 0
                or projection["executed_quantity"] > projection["original_quantity"]):
            raise ValueError("Invalid reconciliation order quantity")
        if projection["broker_order_id"] is None and projection["state"] != "rejected":
            raise ValueError("Reconciled order is missing its broker identity")
        if projection["state"] == "filled" and projection["executed_quantity"] != projection["original_quantity"]:
            raise ValueError("Filled reconciliation projection has incomplete executions")
        if projection["state"] == "rejected" and projection["executed_quantity"] != 0:
            raise ValueError("Rejected reconciliation projection has executions")
        if projection["state"] == "working" and projection["executed_quantity"] >= projection["original_quantity"]:
            raise ValueError("Working reconciliation projection has no remainder")
        if sum(row["quantity"] for row in value["executions"]) != projection["executed_quantity"]:
            raise ValueError("Reconciliation projection disagrees with its executions")
        execution_ids = {row["execution_id"] for row in value["executions"]}
        if any(row["execution_id"] not in execution_ids for row in value["commissions"]):
            raise ValueError("Reconciliation commission has no execution")
    elif value["executions"] or value["commissions"]:
        raise ValueError("Reconciliation evidence has no order projection")
    return value


def _execution(raw):
    value = deepcopy(raw)
    if not isinstance(value, dict) or set(value) != EXECUTION_FIELDS:
        raise ValueError("Invalid execution evidence")
    for key in ("execution_id", "client_order_id", "broker_order_id", "instrument_id"):
        store._identity(value[key], key.replace("_", " "))
    if (not isinstance(value["symbol"], str) or value["currency"] != "USD"
            or value["side"] != "buy"):
        raise ValueError("P4.4 supports synthetic USD entry executions only")
    if type(value["quantity"]) is not int or value["quantity"] <= 0:
        raise ValueError("Execution quantity must be positive whole shares")
    store._decimal_string(value["price_usd"], "execution price", allow_zero=False)
    store._timestamp_string(value["at"], "execution time")
    return value


def _commission(raw):
    value = deepcopy(raw)
    if not isinstance(value, dict) or set(value) != COMMISSION_FIELDS:
        raise ValueError("Invalid commission evidence")
    store._identity(value["commission_id"], "commission id")
    store._identity(value["execution_id"], "commission execution id")
    if value["currency"] != "USD":
        raise ValueError("P4.4 supports USD commissions only")
    store._decimal_string(value["amount_usd"], "commission amount")
    store._timestamp_string(value["at"], "commission time")
    store._version(value["revision"], "commission revision")
    return value


def _snapshot(raw):
    value = deepcopy(raw)
    if not isinstance(value, dict) or set(value) != SNAPSHOT_FIELDS or value["schema"] != SNAPSHOT_SCHEMA:
        raise ValueError("Reconciliation snapshot fields do not match the contract")
    for key in ("snapshot_id", "reconciliation_id", "account_id"):
        store._identity(value[key], key.replace("_", " "))
    if value["environment"] != "synthetic":
        raise ValueError("Only synthetic reconciliation is supported")
    store._timestamp_string(value["at"], "reconciliation snapshot time")
    store._version(value["expected_reconciliation_version"], "expected reconciliation version")
    if (not isinstance(value["completeness"], dict)
            or set(value["completeness"]) != COMPLETENESS_FIELDS
            or any(type(flag) is not bool for flag in value["completeness"].values())):
        raise ValueError("Invalid reconciliation completeness declaration")
    if not all(isinstance(value[key], list) for key in ("orders", "executions", "commissions", "positions", "pending_settlements")):
        raise ValueError("Reconciliation evidence collections must be arrays")
    if len(value["orders"]) > 1 or len(value["positions"]) > 1:
        raise ValueError("Synthetic reconciliation supports one order and one position")
    for row in value["orders"]:
        if not isinstance(row, dict) or set(row) != ORDER_FIELDS or row["state"] not in ORDER_STATES:
            raise ValueError("Invalid order evidence")
        store._identity(row["client_order_id"], "client order id")
        if row["broker_order_id"] is not None:
            store._identity(row["broker_order_id"], "broker order id")
        if (type(row["original_quantity"]) is not int or row["original_quantity"] <= 0
                or type(row["cumulative_executed_quantity"]) is not int
                or row["cumulative_executed_quantity"] < 0):
            raise ValueError("Invalid order quantities")
    value["executions"] = [_execution(row) for row in value["executions"]]
    value["commissions"] = [_commission(row) for row in value["commissions"]]
    if not isinstance(value["currency_cash"], dict) or set(value["currency_cash"]) != {"USD"}:
        raise ValueError("Currency cash must contain exactly USD")
    store._decimal_string(value["currency_cash"]["USD"], "USD settled cash")
    for row in value["positions"]:
        if not isinstance(row, dict) or set(row) != POSITION_FIELDS:
            raise ValueError("Invalid position evidence")
        store._identity(row["instrument_id"], "position instrument id")
        if not isinstance(row["symbol"], str) or row["currency"] != "USD":
            raise ValueError("Invalid synthetic position")
        if type(row["quantity"]) is not int or row["quantity"] <= 0:
            raise ValueError("Position quantity must be positive whole shares")
    store._decimal_string(value["unsettled_usd"], "unsettled USD")
    store._mark(value["mark"])
    return value


def _read(connection):
    if connection.execute("PRAGMA user_version").fetchone()[0] not in (3, 4):
        raise ValueError("Order database requires an explicit P4.4 reconciliation migration")
    row = connection.execute("SELECT payload FROM reconciliation_state WHERE id=1").fetchone()
    if row is None:
        raise ValueError("Reconciliation state missing; explicit migration required")
    state = _state_payload(row[0])
    events = []
    projected = None
    last_at = None
    for expected, (sequence, event_id, kind, payload_sha, raw) in enumerate(connection.execute(
            "SELECT sequence,event_id,kind,payload_sha256,payload FROM reconciliation_events ORDER BY sequence"), 1):
        event = decode(raw)
        if (sequence != expected or kind not in EVENT_KINDS or not isinstance(event, dict)
                or set(event) != {"schema", "event_id", "kind", "at", "committed_version",
                                     "input_sha256", "state"}
                or event["schema"] != EVENT_SCHEMA or event["event_id"] != event_id
                or event["kind"] != kind or event["committed_version"] != sequence
                or store.digest(event) != payload_sha):
            raise ValueError("Invalid reconciliation event sequence or payload")
        base = {key: item for key, item in event.items() if key != "event_id"}
        if event_id != store.digest(base):
            raise ValueError("Reconciliation event identity mismatch")
        at = store._timestamp_string(event["at"], "reconciliation event time")
        if last_at is not None and at < last_at:
            raise ValueError("Reconciliation event time moved backwards")
        last_at = at
        projected = _state_payload(event["state"])
        if projected["version"] != sequence or projected["as_of"] != event["at"]:
            raise ValueError("Reconciliation event projection mismatch")
        events.append(event)
    if state["version"] != len(events) or (events and state != projected):
        raise ValueError("Reconciliation state disagrees with event history")
    if not events and state["version"] != 0:
        raise ValueError("Invalid initial reconciliation version")
    return state, events


def _report(connection, state=None):
    state = state or _read(connection)[0]
    inbox = connection.execute("SELECT COUNT(*) FROM reconciliation_inbox").fetchone()[0]
    return {
        "schema": STATE_SCHEMA, "mode": MODE, "version": state["version"],
        "account_id": state["account_id"], "environment": state["environment"],
        "as_of": state["as_of"], "status": state["status"],
        "last_snapshot_id": state["last_snapshot_id"],
        "unresolved_reasons": state["unresolved_reasons"],
        "order_projection": state["order_projection"],
        "execution_ids": [row["execution_id"] for row in state["executions"]],
        "commission_ids": [row["commission_id"] for row in state["commissions"]],
        "inbox_count": inbox, "live_trading_enabled": False,
    }


def status(path):
    with store.database(path) as connection:
        store._read_state(connection)
        writer._read_writer(connection)
        return _report(connection)


def history(path):
    with store.database(path) as connection:
        state, events = _read(connection)
        store._read_state(connection)
        writer._read_writer(connection)
        return events


def _append(connection, kind, at, input_sha, state):
    state = deepcopy(state)
    state["version"] += 1
    state["as_of"] = at.isoformat()
    base = {"schema": EVENT_SCHEMA, "kind": kind, "at": at.isoformat(),
            "committed_version": state["version"], "input_sha256": input_sha,
            "state": state}
    event = dict(base, event_id=store.digest(base))
    connection.execute("INSERT INTO reconciliation_events VALUES (?, ?, ?, ?, ?)",
                       (state["version"], event["event_id"], kind,
                        store.digest(event), store.pack(event)))
    connection.execute("UPDATE reconciliation_state SET payload=? WHERE id=1", (store.pack(state),))
    return state, event


def _writer_reconciliation_request(reconciliation_id, at, clear=(), add=()):
    return {"schema": WRITER_REQUEST_SCHEMA, "reconciliation_id": reconciliation_id,
            "at": at.isoformat(), "clear_reasons": sorted(set(clear)),
            "add_reasons": sorted(set(add))}


def _disarm(connection, reconciliation_id, at, add, clear=(), submission=None):
    current, submissions, events = writer._read_writer(connection)
    writer._require_monotonic(at, events)
    request = _writer_reconciliation_request(reconciliation_id, at, clear, add)
    current["owner_id"] = current["claim_id"] = current["claimed_at"] = None
    current["disarmed"] = True
    current["unresolved_reasons"] = sorted(
        (set(current["unresolved_reasons"]) - set(clear)) | set(add))
    current, submission, _ = writer._append_event(
        connection, "reconciliation_applied" if submission is not None else "reconciliation_disarmed",
        at, request, current, submission)
    if submission is not None:
        submissions[submission["operation_id"]] = submission
    return current, submissions


def _invalidate_connection(connection, payload, *, writer_already_disarmed=False):
    state, events = _read(connection)
    if not isinstance(payload, dict) or set(payload) != INVALIDATION_FIELDS or payload["schema"] != INVALIDATION_SCHEMA:
        raise ValueError("Reconciliation invalidation fields do not match the contract")
    event_id = store._identity(payload["event_id"], "invalidation event id")
    at = store._timestamp_string(payload["at"], "invalidation time")
    account = store._read_state(connection)
    if at < utc(account["at"]):
        raise ValueError("Reconciliation invalidation predates account state")
    if payload["reason"] not in INVALIDATION_REASONS:
        raise ValueError("Invalid reconciliation reason")
    previous = next((event for event in events if event["input_sha256"] == store.digest(payload)), None)
    if previous is not None:
        return state, True
    if events and at < utc(events[-1]["at"]):
        raise ValueError("Reconciliation event time cannot move backwards")
    _, _, writer_events = writer._read_writer(connection)
    reused = any(
        event["kind"] in ("reconciliation_disarmed", "reconciliation_applied")
        and event["request"]["reconciliation_id"] == event_id
        for event in writer_events)
    if reused:
        reasons = sorted(set(state["unresolved_reasons"] + ["invalidation_identity_conflict"]))
        state.update(status="unresolved", unresolved_reasons=reasons)
        state, _ = _append(connection, "incident", at, store.digest(payload), state)
        conflict_id = "conflict-" + store.digest(payload)[:32]
        _disarm(connection, conflict_id, at, ["invalidation_identity_conflict"])
        return state, False
    reasons = sorted(set(state["unresolved_reasons"] + ["reconciliation_required"]))
    state.update(status="required", unresolved_reasons=reasons)
    state, _ = _append(connection, "invalidated", at, store.digest(payload), state)
    if not writer_already_disarmed:
        _disarm(connection, event_id, at, ["reconciliation_required"])
    else:
        current, submissions, writer_events = writer._read_writer(connection)
        request = _writer_reconciliation_request(event_id, at, (), ["reconciliation_required"])
        current["unresolved_reasons"] = sorted(set(current["unresolved_reasons"] + ["reconciliation_required"]))
        writer._append_event(connection, "reconciliation_disarmed", at, request, current)
    return state, False


def invalidate(path, payload):
    with store.database(path, write=True) as connection:
        store._read_state(connection)
        state, duplicate = _invalidate_connection(connection, payload)
        result = _report(connection, state)
        result.update(outcome=state["status"], duplicate=duplicate)
        return result


def _evidence_by_id(rows, key):
    output = {}
    conflict = False
    for row in rows:
        identity = row[key]
        if identity in output:
            if output[identity] != row:
                conflict = True
            continue
        output[identity] = row
    return output, conflict


def _unresolved(connection, state, snapshot, reasons, kind="snapshot_unresolved"):
    at = utc(snapshot["at"])
    if set(reasons) & DURABLE_REASONS:
        kind = "incident"
    reasons = sorted(set(state["unresolved_reasons"] + reasons))
    state.update(status="unresolved", last_snapshot_id=snapshot["snapshot_id"],
                 unresolved_reasons=reasons)
    state, _ = _append(connection, kind, at, store.digest(snapshot), state)
    _disarm(connection, snapshot["reconciliation_id"], at, reasons)
    result = _report(connection, state)
    result.update(outcome="unresolved", duplicate=False)
    return result


def _validate_complete(state, snapshot, submissions):
    reasons = []
    prior_executions, prior_execution_conflict = _evidence_by_id(
        state["executions"], "execution_id")
    executions, execution_conflict = _evidence_by_id(snapshot["executions"], "execution_id")
    prior_commissions, prior_commission_conflict = _evidence_by_id(
        state["commissions"], "commission_id")
    commissions, commission_conflict = _evidence_by_id(snapshot["commissions"], "commission_id")
    if prior_execution_conflict or prior_commission_conflict:
        raise ValueError("Stored reconciliation evidence contains conflicting identities")
    if execution_conflict:
        reasons.append("execution_identity_conflict")
    if commission_conflict:
        reasons.append("commission_identity_conflict")
    for identity, row in prior_executions.items():
        if executions.get(identity) != row:
            reasons.append("execution_history_changed")
    for identity, row in prior_commissions.items():
        current = commissions.get(identity)
        if current != row:
            unchanged = {key: value for key, value in row.items()
                         if key not in ("amount_usd", "revision", "at")}
            current_unchanged = ({key: value for key, value in current.items()
                                  if key not in ("amount_usd", "revision", "at")}
                                 if current is not None else None)
            if (current is None or current_unchanged != unchanged
                    or current["revision"] <= row["revision"]
                    or utc(current["at"]) < utc(row["at"])):
                reasons.append("commission_history_changed")
    if any(row["execution_id"] not in executions for row in commissions.values()):
        reasons.append("commission_execution_missing")
    expected_cash = money(state["baseline_settled_cash_usd"])
    expected_cash -= sum(money(row["price_usd"]) * row["quantity"] for row in executions.values())
    expected_cash -= sum(money(row["amount_usd"]) for row in commissions.values())
    if money(snapshot["currency_cash"]["USD"]) != expected_cash:
        reasons.append("currency_cash_mismatch")
    if money(snapshot["unsettled_usd"]) != 0 or snapshot["pending_settlements"]:
        reasons.append("settlement_mismatch")
    # Expired authority is a local tombstone, never evidence of a broker order.
    dispatched = [row for row in submissions.values() if row["reason"] != "expired_authority"]
    submission = (max(dispatched, key=lambda row: row["last_event_version"])
                  if dispatched else None)
    older = [row for row in dispatched if row is not submission]
    if any(row["state"] not in ("rejected", "cancelled") for row in older):
        reasons.append("multiple_submissions_unsupported")
        return reasons, None, None, executions, commissions
    if submission is None:
        if snapshot["orders"] or executions or commissions or snapshot["positions"]:
            reasons.append("external_activity_unknown")
        return reasons, None, None, executions, commissions
    command = submission["command"]
    order = snapshot["orders"][0] if snapshot["orders"] else None
    if order is None:
        reasons.append("order_outcome_unknown")
        return reasons, submission, None, executions, commissions
    if order["client_order_id"] != command["client_order_id"]:
        reasons.append("client_order_mismatch")
    if order["original_quantity"] != command["quantity"]:
        reasons.append("original_quantity_mismatch")
    known_broker = submission["broker_order_id"]
    if order["broker_order_id"] is None and order["state"] != "rejected":
        reasons.append("broker_order_id_missing")
    elif known_broker is not None and order["broker_order_id"] != known_broker:
        reasons.append("broker_order_identity_changed")
    linked = [row for row in executions.values() if row["client_order_id"] == command["client_order_id"]]
    if len(linked) != len(executions):
        reasons.append("external_execution_unknown")
    for row in linked:
        if (row["broker_order_id"] != order["broker_order_id"]
                or row["instrument_id"] != command["instrument_id"]
                or row["symbol"] != command["symbol"]):
            reasons.append("execution_order_mismatch")
    executed = sum(row["quantity"] for row in linked)
    if executed > command["quantity"]:
        reasons.append("execution_overfill")
    if order["cumulative_executed_quantity"] != executed:
        reasons.append("order_execution_quantity_mismatch")
    if order["state"] == "filled" and executed != command["quantity"]:
        reasons.append("filled_quantity_mismatch")
    if order["state"] == "working" and executed >= command["quantity"]:
        reasons.append("working_quantity_mismatch")
    if order["state"] == "cancelled" and executed == command["quantity"]:
        reasons.append("cancelled_quantity_mismatch")
    if order["state"] == "rejected" and executed:
        reasons.append("rejected_order_has_execution")
    prior_order = state["order_projection"]
    if prior_order is not None and prior_order["intent_id"] == submission["intent_id"]:
        allowed = {
            "filled": {"filled"}, "rejected": {"rejected"},
            "cancelled": {"cancelled", "filled"}, "working": ORDER_STATES,
        }
        if order["state"] not in allowed[prior_order["state"]]:
            reasons.append("order_state_regression")
    position = snapshot["positions"][0] if snapshot["positions"] else None
    position_quantity = 0 if position is None else position["quantity"]
    if position is not None and (position["instrument_id"] != command["instrument_id"]
                                 or position["symbol"] != command["symbol"]):
        reasons.append("position_identity_mismatch")
    if position_quantity != executed:
        reasons.append("position_quantity_mismatch")
    return reasons, submission, order, executions, commissions


def _adjust_account(connection, account, snapshot, submission, order, executions, commissions, intent):
    executed = sum(row["quantity"] for row in executions.values())
    reserves = {key: account[key] for key in (
        "reserved_cash_usd", "reserved_exposure_gbp", "reserved_loss_gbp")}
    if intent is not None:
        proposal = intent["proposal"]
        remaining = proposal["quantity"] - executed if order["state"] == "working" else 0
        fees = sum(money(row["amount_usd"]) for row in commissions.values())
        cash_reserve = D(remaining) * (money(proposal["limit_price_usd"])
                                      + money(proposal["slippage_usd_per_share"]))
        if remaining:
            cash_reserve += max(money(proposal["entry_fee_usd"]) - fees, D("0"))
        if remaining or executed:
            cash_reserve += money(proposal["exit_fee_usd"])
        retain_risk = remaining > 0 or executed > 0
        original = intent["reservation"]
        reserves = {
            "reserved_cash_usd": str(cash_reserve if cash_reserve else D("0")),
            "reserved_exposure_gbp": original["exposure_gbp"] if retain_risk else "0",
            "reserved_loss_gbp": original["planned_loss_gbp"] if retain_risk else "0",
        }
    mark = store._mark(snapshot["mark"])
    assessment = assess(mark, store._mark(account["session_start"]),
                        store._mark(account["week_start"]), tuple(account["halt_reasons"]))
    version = account["version"] + 1
    adjustment = {
        "reconciliation_id": snapshot["reconciliation_id"],
        "snapshot_id": snapshot["snapshot_id"],
        "intent_id": submission["intent_id"] if submission is not None else None,
        "at": utc(snapshot["at"]).isoformat(),
        "settled_cash_usd": str(money(snapshot["currency_cash"]["USD"])),
        "position_quantity": executed, "mark": store._mark_payload(mark),
        "halt_reasons": list(assessment.halt_reasons),
        **reserves,
        "committed_version": version,
    }
    connection.execute("INSERT INTO reconciliation_adjustments VALUES (?, ?, ?)",
                       (adjustment["reconciliation_id"], version, store.pack(adjustment)))
    connection.execute("INSERT INTO audit VALUES (?, 'reconciliation', ?, ?)",
                       (version, adjustment["reconciliation_id"], store.digest(adjustment)))
    account.update(version=version, at=adjustment["at"],
                   settled_cash_usd=adjustment["settled_cash_usd"],
                   position_quantity=executed, mark=adjustment["mark"],
                   halt_reasons=adjustment["halt_reasons"],
                   reserved_cash_usd=adjustment["reserved_cash_usd"],
                   reserved_exposure_gbp=adjustment["reserved_exposure_gbp"],
                   reserved_loss_gbp=adjustment["reserved_loss_gbp"])
    store._write_state(connection, account)
    return adjustment


def apply(path, raw):
    snapshot = _snapshot(raw)
    with store.database(path, write=True) as connection:
        if connection.execute("PRAGMA user_version").fetchone()[0] == store.REDUCING_DATABASE_VERSION:
            from . import order_sell_reconciliation
            sell, _ = order_sell_reconciliation._read(connection)
            if sell["version"]:
                raise ValueError("Use reducing reconciliation after sell evidence begins")
        account = store._read_state(connection)
        state, events = _read(connection)
        current_writer, submissions, writer_events = writer._read_writer(connection)
        if snapshot["account_id"] != state["account_id"]:
            raise ValueError("Reconciliation account mismatch")
        existing = connection.execute(
            "SELECT payload_sha256,payload FROM reconciliation_inbox WHERE snapshot_id=?",
            (snapshot["snapshot_id"],)).fetchone()
        if existing is not None:
            if existing[0] == store.digest(snapshot) and decode(existing[1]) == snapshot:
                result = _report(connection, state)
                result.update(outcome="reconciled" if state["status"] == "reconciled" else "unresolved",
                              duplicate=True)
                return result
            conflict = deepcopy(snapshot)
            conflict["reconciliation_id"] = "conflict-" + store.digest(snapshot)[:32]
            prior_conflict = next((event for event in events
                                   if event["kind"] == "incident"
                                   and event["input_sha256"] == store.digest(conflict)), None)
            if prior_conflict is not None:
                result = _report(connection, state)
                result.update(outcome="unresolved", duplicate=True)
                return result
            at = utc(snapshot["at"])
            if events and at < utc(events[-1]["at"]):
                raise ValueError("Reconciliation event time cannot move backwards")
            return _unresolved(connection, state, conflict, ["snapshot_identity_conflict"], "incident")
        reused_reconciliation = next((decode(row[0]) for row in connection.execute(
            "SELECT payload FROM reconciliation_inbox")
            if decode(row[0])["reconciliation_id"] == snapshot["reconciliation_id"]), None)
        if reused_reconciliation is not None:
            at = utc(snapshot["at"])
            if events and at < utc(events[-1]["at"]):
                raise ValueError("Reconciliation event time cannot move backwards")
            conflict = deepcopy(snapshot)
            conflict["reconciliation_id"] = "conflict-" + store.digest(snapshot)[:32]
            connection.execute("INSERT INTO reconciliation_inbox VALUES (?, ?, ?)",
                               (snapshot["snapshot_id"], store.digest(snapshot), store.pack(snapshot)))
            return _unresolved(connection, state, conflict,
                               ["reconciliation_identity_conflict"], "incident")
        if snapshot["expected_reconciliation_version"] != state["version"]:
            raise ValueError("Reconciliation version changed; read status before retrying")
        at = utc(snapshot["at"])
        if at < utc(account["at"]):
            raise ValueError("Reconciliation snapshot predates account state")
        if store._periods(at.isoformat()) != (account["session"], account["week"]):
            raise ValueError("Reconciliation requires a reviewed period transition")
        if events and at < utc(events[-1]["at"]):
            raise ValueError("Reconciliation event time cannot move backwards")
        if writer_events and at < utc(writer_events[-1]["at"]):
            raise ValueError("Reconciliation predates writer evidence")
        connection.execute("INSERT INTO reconciliation_inbox VALUES (?, ?, ?)",
                           (snapshot["snapshot_id"], store.digest(snapshot), store.pack(snapshot)))
        if not all(snapshot["completeness"].values()):
            return _unresolved(connection, state, snapshot, ["snapshot_incomplete"])
        reasons, submission, order, executions, commissions = _validate_complete(
            state, snapshot, submissions)
        if reasons:
            return _unresolved(connection, state, snapshot, reasons)
        intent = None
        if submission is not None:
            latest_reserved = next((record for (raw,) in connection.execute(
                "SELECT payload FROM intents ORDER BY committed_version DESC")
                if (record := store._record_payload(raw))["state"] == "reserved"), None)
            if latest_reserved is not None and latest_reserved["intent_id"] == submission["intent_id"]:
                intent = latest_reserved
            elif executions or order["state"] == "working":
                # Late exposure cannot overwrite a newer attempt's allocation.
                return _unresolved(connection, state, snapshot, ["reservation_owner_conflict"])
        adjustment = _adjust_account(connection, account, snapshot, submission, order,
                                     executions, commissions, intent)
        if submission is None:
            clear = sorted(TRANSIENT_REASONS | {"submission_unknown", "submission_rejected"})
            remaining = sorted(set(current_writer["unresolved_reasons"]) - set(clear))
            state.update(status="reconciled", last_snapshot_id=snapshot["snapshot_id"],
                         unresolved_reasons=remaining, executions=[], commissions=[],
                         order_projection=None)
            if remaining:
                state["status"] = "unresolved"
            state, _ = _append(connection, "snapshot_applied", at, store.digest(snapshot), state)
            _disarm(connection, snapshot["reconciliation_id"], at,
                    remaining, clear)
            result = _report(connection, state)
            result.update(outcome=state["status"], duplicate=False, adjustment=adjustment,
                          account=store._report(account, state))
            return result
        executed = order["cumulative_executed_quantity"]
        if order["state"] == "working":
            submission_state = "acknowledged" if executed == 0 else "partially_filled"
            reason = None
        else:
            submission_state = order["state"]
            reason = None if order["state"] == "filled" else "reconciled_" + order["state"]
        updated = deepcopy(submission)
        updated.update(state=submission_state, broker_order_id=order["broker_order_id"],
                       reason=reason, resolved_at=at.isoformat())
        clear = sorted(TRANSIENT_REASONS | {"submission_unknown", "submission_rejected"})
        remaining_writer_reasons = sorted(set(current_writer["unresolved_reasons"]) - set(clear))
        state.update(status="reconciled" if not remaining_writer_reasons else "unresolved",
                     last_snapshot_id=snapshot["snapshot_id"],
                     unresolved_reasons=remaining_writer_reasons,
                     executions=[executions[key] for key in sorted(executions)],
                     commissions=[commissions[key] for key in sorted(commissions)],
                     order_projection={
                         "intent_id": submission["intent_id"],
                         "client_order_id": order["client_order_id"],
                         "broker_order_id": order["broker_order_id"], "state": order["state"],
                         "original_quantity": order["original_quantity"],
                         "executed_quantity": executed,
                     })
        state, _ = _append(connection, "snapshot_applied", at, store.digest(snapshot), state)
        _disarm(connection, snapshot["reconciliation_id"], at,
                remaining_writer_reasons, clear, updated)
        if connection.execute("PRAGMA user_version").fetchone()[0] == store.REDUCING_DATABASE_VERSION:
            from . import order_cancellation
            projection = state["order_projection"]
            order_cancellation.apply_evidence(connection, at, [{
                "client_order_id": projection["client_order_id"],
                "order_id": projection["broker_order_id"], "side": "buy",
                "state": projection["state"], "original_quantity": projection["original_quantity"],
                "cumulative_executed_quantity": projection["executed_quantity"],
            }], snapshot["reconciliation_id"])
        result = _report(connection, state)
        result.update(outcome=state["status"], duplicate=False, adjustment=adjustment,
                      account=store._report(account, state))
        return result
