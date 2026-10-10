"""Cumulative v4 buy/sell accounting from supplied synthetic evidence; no dispatch."""
from copy import deepcopy
from datetime import date
from decimal import Decimal as D
from zoneinfo import ZoneInfo

from .ledger import utc
from .risk import assess, money
from .settlement import (CASH_RELEASE_POLICY, SETTLEMENT_CALENDAR_ID,
                         cash_available_at, settlement_date)
from . import order_allocations, order_reconciliation, order_store as store, order_writer


SNAPSHOT_SCHEMA = "synthetic-reducing-reconciliation-v1"
STATE_SCHEMA = "reducing-reconciliation-state-v1"
EVENT_SCHEMA = "reducing-reconciliation-event-v1"
REPORT_SCHEMA = "reducing-reconciliation-report-v1"
MODE = "synthetic_reducing_reconciliation_only"
COMPLETENESS_FIELDS = {
    "orders", "executions", "positions", "currency_cash", "commissions", "settlement",
}
SNAPSHOT_FIELDS = {
    "schema", "snapshot_id", "reconciliation_id", "account_id", "environment", "at",
    "expected_reducing_reconciliation_version", "expected_account_version",
    "expected_writer_version", "expected_allocation_version", "completeness", "orders",
    "executions", "commissions", "positions", "currency_cash", "unsettled_usd",
    "pending_settlements", "mark",
}
ORDER_FIELDS = {
    "client_order_id", "order_id", "side", "state", "original_quantity",
    "cumulative_executed_quantity",
}
EXECUTION_FIELDS = {
    "execution_id", "client_order_id", "order_id", "instrument_id", "symbol", "currency",
    "side", "quantity", "price_usd", "at",
}
COMMISSION_FIELDS = {
    "commission_id", "execution_id", "currency", "amount_usd", "at", "revision", "final",
}
POSITION_FIELDS = {"instrument_id", "symbol", "currency", "quantity"}
PENDING_FIELDS = {
    "execution_id", "gross_usd", "fee_usd", "fee_status", "net_usd", "settles_on",
    "available_at", "settlement_calendar_id", "cash_release_policy",
}
ORDER_STATES = {"working", "filled", "unknown"}
DURABLE_REASONS = {
    "snapshot_identity_conflict", "reconciliation_identity_conflict",
    "execution_identity_conflict", "execution_history_changed",
    "commission_identity_conflict", "commission_history_changed",
    "unknown_order", "order_identity_changed", "order_side_mismatch", "execution_order_mismatch",
    "execution_identity_changed", "execution_overfill", "external_activity_unknown",
    "negative_position", "position_identity_mismatch", "position_quantity_mismatch",
    "sell_before_allocation", "buy_before_submission", "cash_history_mismatch",
    "pending_settlement_mismatch", "negative_pending_proceeds",
    "sell_commitment_exceeds_holdings", "execution_time_invalid",
}
TRANSIENT_REASONS = {"snapshot_incomplete", "fee_incomplete"}


def _initialize_tables(connection, account_id, at):
    state = {
        "schema": STATE_SCHEMA, "version": 0, "account_id": account_id,
        "environment": "synthetic", "as_of": at.isoformat(), "status": "reconciled",
        "last_snapshot_id": None, "account_version": 0, "entry_intent_id": None,
        "instrument_id": None, "verified_quantity": 0, "committed_sell_quantity": 0,
        "incurred_exit_fees_usd": "0", "outstanding_exit_fees_usd": "0",
        "unresolved_reasons": [], "orders": [], "executions": [], "commissions": [],
        "pending_lots": [], "live_trading_enabled": False,
    }
    connection.execute("CREATE TABLE reducing_reconciliation_state "
                       "(id INTEGER PRIMARY KEY CHECK(id=1), payload TEXT NOT NULL)")
    connection.execute("CREATE TABLE reducing_reconciliation_inbox "
                       "(receipt_id TEXT PRIMARY KEY, snapshot_id TEXT NOT NULL, reconciliation_id TEXT NOT NULL, "
                       "payload_sha256 TEXT NOT NULL, payload TEXT NOT NULL)")
    connection.execute("CREATE INDEX reducing_reconciliation_snapshot "
                       "ON reducing_reconciliation_inbox(snapshot_id)")
    connection.execute("CREATE INDEX reducing_reconciliation_identity "
                       "ON reducing_reconciliation_inbox(reconciliation_id)")
    connection.execute("CREATE TABLE reducing_reconciliation_events "
                       "(sequence INTEGER PRIMARY KEY, event_id TEXT UNIQUE NOT NULL, "
                       "kind TEXT NOT NULL, input_sha256 TEXT NOT NULL, payload_sha256 TEXT NOT NULL, "
                       "payload TEXT NOT NULL)")
    connection.execute("INSERT INTO reducing_reconciliation_state VALUES (1, ?)",
                       (store.pack(state),))


def _identity(value, label):
    return store._identity(value, label)


def _order(raw):
    value = deepcopy(raw)
    if not isinstance(value, dict) or set(value) != ORDER_FIELDS:
        raise ValueError("Invalid reducing reconciliation order")
    for field in ("client_order_id", "order_id"):
        _identity(value[field], field.replace("_", " "))
    if value["side"] not in ("buy", "sell") or value["state"] not in ORDER_STATES:
        raise ValueError("Invalid reducing reconciliation order side or state")
    for field in ("original_quantity", "cumulative_executed_quantity"):
        if type(value[field]) is not int or value[field] < 0:
            raise ValueError("Invalid reducing reconciliation order quantity")
    if value["original_quantity"] <= 0:
        raise ValueError("Reducing reconciliation original quantity must be positive")
    return value


def _execution(raw):
    value = deepcopy(raw)
    if not isinstance(value, dict) or set(value) != EXECUTION_FIELDS:
        raise ValueError("Invalid reducing reconciliation execution")
    for field in ("execution_id", "client_order_id", "order_id", "instrument_id", "symbol"):
        _identity(value[field], field.replace("_", " "))
    if value["currency"] != "USD" or value["side"] not in ("buy", "sell"):
        raise ValueError("Only USD buy/sell executions are supported")
    if type(value["quantity"]) is not int or value["quantity"] <= 0:
        raise ValueError("Execution quantity must be a positive whole number")
    store._decimal_string(value["price_usd"], "execution price", allow_zero=False)
    store._timestamp_string(value["at"], "execution time")
    return value


def _commission(raw):
    value = deepcopy(raw)
    if not isinstance(value, dict) or set(value) != COMMISSION_FIELDS:
        raise ValueError("Invalid reducing reconciliation commission")
    _identity(value["commission_id"], "commission id")
    _identity(value["execution_id"], "commission execution id")
    if value["currency"] != "USD" or type(value["final"]) is not bool:
        raise ValueError("Invalid reducing reconciliation commission currency or finality")
    store._decimal_string(value["amount_usd"], "commission amount")
    store._timestamp_string(value["at"], "commission time")
    store._version(value["revision"], "commission revision")
    return value


def _position(raw):
    value = deepcopy(raw)
    if not isinstance(value, dict) or set(value) != POSITION_FIELDS:
        raise ValueError("Invalid reducing reconciliation position")
    for field in ("instrument_id", "symbol"):
        _identity(value[field], "position " + field.replace("_", " "))
    if value["currency"] != "USD" or type(value["quantity"]) is not int or value["quantity"] <= 0:
        raise ValueError("Invalid reducing reconciliation position")
    return value


def _pending(raw):
    value = deepcopy(raw)
    if not isinstance(value, dict) or set(value) != PENDING_FIELDS:
        raise ValueError("Invalid pending settlement evidence")
    _identity(value["execution_id"], "pending execution id")
    for field in ("gross_usd", "fee_usd", "net_usd"):
        store._decimal_string(value[field], field.replace("_", " "), allow_negative=field == "net_usd")
    if value["fee_status"] not in ("missing", "provisional", "final"):
        raise ValueError("Invalid pending fee status")
    if (value["settlement_calendar_id"] != SETTLEMENT_CALENDAR_ID
            or value["cash_release_policy"] != CASH_RELEASE_POLICY):
        raise ValueError("Pending settlement policy mismatch")
    due = date.fromisoformat(value["settles_on"])
    if due.isoformat() != value["settles_on"]:
        raise ValueError("Invalid pending settlement date")
    store._timestamp_string(value["available_at"], "pending availability")
    return value


def _snapshot(raw):
    value = deepcopy(raw)
    if not isinstance(value, dict) or set(value) != SNAPSHOT_FIELDS or value["schema"] != SNAPSHOT_SCHEMA:
        raise ValueError("Reducing reconciliation snapshot fields do not match the contract")
    for field in ("snapshot_id", "reconciliation_id", "account_id"):
        _identity(value[field], field.replace("_", " "))
    if value["environment"] != "synthetic":
        raise ValueError("Only synthetic reducing reconciliation is supported")
    store._timestamp_string(value["at"], "reducing reconciliation time")
    for field in ("expected_reducing_reconciliation_version", "expected_account_version",
                  "expected_writer_version", "expected_allocation_version"):
        store._version(value[field], field.replace("_", " "))
    if (not isinstance(value["completeness"], dict)
            or set(value["completeness"]) != COMPLETENESS_FIELDS
            or any(type(item) is not bool for item in value["completeness"].values())):
        raise ValueError("Invalid reducing reconciliation completeness")
    for field in ("orders", "executions", "commissions", "positions", "pending_settlements"):
        if not isinstance(value[field], list):
            raise ValueError("Reducing reconciliation evidence collections must be lists")
    value["orders"] = sorted(
        (_order(item) for item in value["orders"]),
        key=lambda item: item["client_order_id"])
    value["executions"] = sorted(
        (_execution(item) for item in value["executions"]),
        key=lambda item: item["execution_id"])
    value["commissions"] = sorted(
        (_commission(item) for item in value["commissions"]),
        key=lambda item: (item["execution_id"], item["revision"], item["commission_id"]))
    value["positions"] = sorted(
        (_position(item) for item in value["positions"]),
        key=lambda item: (item["instrument_id"], item["symbol"]))
    value["pending_settlements"] = sorted(
        (_pending(item) for item in value["pending_settlements"]),
        key=lambda item: item["execution_id"])
    if not isinstance(value["currency_cash"], dict) or set(value["currency_cash"]) != {"USD"}:
        raise ValueError("Reducing reconciliation requires one USD cash balance")
    store._decimal_string(value["currency_cash"]["USD"], "settled USD cash")
    store._decimal_string(value["unsettled_usd"], "unsettled USD", allow_negative=True)
    store._mark(value["mark"])
    return value


def _unique(rows, key):
    output = {}
    conflict = False
    for row in rows:
        identity = row[key]
        if identity in output and output[identity] != row:
            conflict = True
        output.setdefault(identity, row)
    return output, conflict


def _latest_commissions(rows):
    by_id, conflict = _unique(rows, "commission_id")
    by_execution = {}
    for row in by_id.values():
        prior = by_execution.get(row["execution_id"])
        if prior is not None:
            if row["commission_id"] != prior["commission_id"]:
                conflict = True
            if row["revision"] == prior["revision"] and row != prior:
                conflict = True
            if row["revision"] <= prior["revision"]:
                continue
        by_execution[row["execution_id"]] = row
    return by_id, by_execution, conflict


def _fee_extends(current, prior):
    """A fee may keep its facts or advance revision without changing identity."""
    if current is None:
        return False
    if all(current[key] == value for key, value in prior.items()):
        return True
    return (all(current[key] == prior[key] for key in
                ("commission_id", "execution_id", "currency"))
            and current["revision"] > prior["revision"]
            and utc(current["at"]) >= utc(prior["at"])
            and (not prior.get("final", False) or current["final"]))


def _lot(execution, commission, fee_bound):
    gross = money(execution["price_usd"]) * execution["quantity"]
    if commission is None:
        fee, status = fee_bound, "missing"
    else:
        fee = money(commission["amount_usd"])
        status = "final" if commission["final"] else "provisional"
    net = gross - fee
    trade_session = utc(execution["at"]).astimezone(ZoneInfo("America/New_York")).date().isoformat()
    due = settlement_date(trade_session)
    return {
        "execution_id": execution["execution_id"], "gross_usd": str(gross),
        "fee_usd": str(fee), "fee_status": status, "net_usd": str(net),
        "settles_on": due.isoformat(), "available_at": cash_available_at(due).isoformat(),
        "settlement_calendar_id": SETTLEMENT_CALENDAR_ID,
        "cash_release_policy": CASH_RELEASE_POLICY,
    }


def _basis_adjustment(connection, version):
    row = connection.execute(
        "SELECT payload FROM reconciliation_adjustments WHERE committed_version=?", (version,)).fetchone()
    if row is None:
        raise ValueError("Reducing reconciliation requires a reconciled account version")
    return store._adjustment_payload(row[0])


def _entry_reconciliation_ids(connection):
    return {store.decode(row[0])["reconciliation_id"] for row in connection.execute(
        "SELECT payload FROM reconciliation_inbox")}


def _derive(connection, snapshot, prior_state):
    if not all(snapshot["completeness"].values()):
        return {"reasons": ["snapshot_incomplete"]}
    reasons = []
    orders, order_conflict = _unique(snapshot["orders"], "client_order_id")
    executions, execution_conflict = _unique(snapshot["executions"], "execution_id")
    commissions_by_id, commissions, commission_conflict = _latest_commissions(snapshot["commissions"])
    if order_conflict:
        reasons.append("order_identity_changed")
    if len({row["order_id"] for row in orders.values()}) != len(orders):
        reasons.append("order_identity_changed")
    if execution_conflict:
        reasons.append("execution_identity_conflict")
    if commission_conflict:
        reasons.append("commission_identity_conflict")
    prior_executions = {row["execution_id"]: row for row in prior_state["executions"]}
    for identity, row in prior_executions.items():
        if executions.get(identity) != row:
            reasons.append("execution_history_changed")
    prior_orders = {row["client_order_id"]: row for row in prior_state["orders"]}
    for identity, row in prior_orders.items():
        current = orders.get(identity)
        if (current is None or any(current[key] != row[key]
                                   for key in ("client_order_id", "order_id", "side",
                                               "original_quantity"))
                or current["cumulative_executed_quantity"] < row["cumulative_executed_quantity"]
                or (row["state"] == "filled" and current["state"] != "filled")):
            reasons.append("order_identity_changed")
    prior_commissions, _, _ = _latest_commissions(prior_state["commissions"])
    for identity, row in prior_commissions.items():
        current = commissions_by_id.get(identity)
        if not _fee_extends(current, row):
            reasons.append("commission_history_changed")

    allocation_state, allocation_records, _ = order_allocations._read(connection)
    reserved = {row["client_order_id"]: row for row in allocation_records
                if row["state"] == "reserved"
                and row["committed_version"] <= snapshot["expected_allocation_version"]}
    entry = connection.execute(
        "SELECT payload FROM intents WHERE intent_id=?", (allocation_state["entry_intent_id"],)).fetchone()
    if entry is None:
        raise ValueError("Reducing reconciliation entry intent is missing")
    intent = store._record_payload(entry[0])
    proposal = intent["proposal"]
    instrument = proposal["instrument_id"]
    submissions = {row["client_order_id"]: row for row in order_writer._read_writer(connection)[1].values()}
    entry_state, _ = order_reconciliation._read(connection)
    entry_projection = entry_state["order_projection"]
    entry_order = orders.get(proposal["client_order_id"])
    if entry_projection is None or entry_order is None:
        reasons.append("cash_history_mismatch")
    else:
        if (entry_order["order_id"] != entry_projection["broker_order_id"]
                or entry_order["original_quantity"] != entry_projection["original_quantity"]
                or entry_order["side"] != "buy"
                or entry_order["cumulative_executed_quantity"] < entry_projection["executed_quantity"]
                or (entry_projection["state"] == "filled" and entry_order["state"] != "filled")):
            reasons.append("cash_history_mismatch")
    for retained in entry_state["executions"]:
        converted = {("order_id" if key == "broker_order_id" else key): value
                     for key, value in retained.items()}
        if executions.get(retained["execution_id"]) != converted:
            reasons.append("cash_history_mismatch")
    for retained in entry_state["commissions"]:
        current = commissions_by_id.get(retained["commission_id"])
        if not _fee_extends(current, retained):
            reasons.append("cash_history_mismatch")
    known_clients = set(reserved) | set(submissions)
    if set(orders) - known_clients:
        reasons.append("unknown_order")
    if any(row["client_order_id"] not in orders for row in executions.values()):
        reasons.append("external_activity_unknown")
    if any(row["execution_id"] not in executions for row in commissions_by_id.values()):
        reasons.append("external_activity_unknown")

    buy_quantity = sell_quantity = 0
    buy_cost = D("0")
    buy_fees = D("0")
    sell_fees_final = D("0")
    committed_sell = 0
    lots = []
    incomplete_fees = False
    for client_id, order in orders.items():
        if client_id in submissions:
            mapping, expected_side = submissions[client_id], "buy"
        elif client_id in reserved:
            mapping, expected_side = reserved[client_id], "sell"
        else:
            mapping, expected_side = None, order["side"]
        if mapping is None:
            continue
        if order["side"] != expected_side:
            reasons.append("order_side_mismatch")
        expected_quantity = (mapping["command"]["quantity"] if expected_side == "buy"
                             else mapping["quantity"])
        expected_instrument = (mapping["command"]["instrument_id"] if expected_side == "buy"
                               else mapping["request"]["instrument_id"])
        if order["original_quantity"] != expected_quantity:
            reasons.append("order_identity_changed")
        linked = sorted((row for row in executions.values() if row["client_order_id"] == client_id),
                        key=lambda row: row["execution_id"])
        if any(row["order_id"] != order["order_id"] or row["instrument_id"] != expected_instrument
               or row["symbol"] != proposal["symbol"] or row["side"] != expected_side
               or row["currency"] != "USD" for row in linked):
            reasons.append("execution_order_mismatch")
        executed = sum(row["quantity"] for row in linked)
        if executed != order["cumulative_executed_quantity"]:
            reasons.append("order_identity_changed")
        if executed > expected_quantity:
            reasons.append("execution_overfill")
        if ((order["state"] == "filled" and executed != expected_quantity)
                or (order["state"] == "working" and executed >= expected_quantity)):
            reasons.append("order_identity_changed")
        fee_bound_remaining = (money(mapping["fee_bound_usd"])
                               if expected_side == "sell" else D("0"))
        for execution in linked:
            threshold = (mapping["marked_at"] if expected_side == "buy"
                         else mapping["request"]["decision_at"])
            if utc(execution["at"]) < utc(threshold) or utc(execution["at"]) > utc(snapshot["at"]):
                reasons.append("buy_before_submission" if expected_side == "buy"
                               else "sell_before_allocation")
            try:
                bounds = store.session_bounds(
                    utc(execution["at"]).astimezone(ZoneInfo("America/New_York")).date().isoformat())
            except ValueError:
                bounds = None
            if bounds is None or not bounds[0] <= utc(execution["at"]) < bounds[1]:
                reasons.append("execution_time_invalid")
            commission = commissions.get(execution["execution_id"])
            if commission is not None and not utc(execution["at"]) <= utc(commission["at"]) <= utc(snapshot["at"]):
                reasons.append("commission_history_changed")
            if expected_side == "buy":
                buy_quantity += execution["quantity"]
                buy_cost += money(execution["price_usd"]) * execution["quantity"]
                if commission is None:
                    incomplete_fees = True
                else:
                    buy_fees += money(commission["amount_usd"])
                    incomplete_fees |= not commission["final"]
            else:
                sell_quantity += execution["quantity"]
                try:
                    lot = _lot(execution, commission, fee_bound_remaining)
                except ValueError:
                    reasons.append("execution_time_invalid")
                    continue
                lots.append(lot)
                incomplete_fees |= lot["fee_status"] != "final"
                fee_bound_remaining = max(fee_bound_remaining - money(lot["fee_usd"]), D("0"))
                if lot["fee_status"] == "final":
                    sell_fees_final += money(lot["fee_usd"])
        if expected_side == "sell" and order["state"] in ("working", "unknown"):
            committed_sell += expected_quantity - executed

    # A reserved allocation absent from complete order evidence remains fully committed.
    committed_sell += sum(row["quantity"] for key, row in reserved.items() if key not in orders)
    quantity = buy_quantity - sell_quantity
    if quantity < 0:
        reasons.append("negative_position")
    if committed_sell > quantity:
        reasons.append("sell_commitment_exceeds_holdings")
    positions = snapshot["positions"]
    observed = 0 if not positions else positions[0]["quantity"]
    if (len(positions) > 1 or (positions and
            (positions[0]["instrument_id"] != instrument or positions[0]["symbol"] != proposal["symbol"]
             or positions[0]["currency"] != "USD"))):
        reasons.append("position_identity_mismatch")
    if observed != quantity:
        reasons.append("position_quantity_mismatch")
    baseline = order_allocations._baseline(connection)
    expected_cash = money(baseline["settled_cash_usd"]) - buy_cost - buy_fees
    if money(snapshot["currency_cash"]["USD"]) != expected_cash:
        reasons.append("cash_history_mismatch")
    lots.sort(key=lambda row: row["execution_id"])
    if any(money(row["net_usd"]) < 0 for row in lots):
        reasons.append("negative_pending_proceeds")
    if (snapshot["pending_settlements"] != lots
            or money(snapshot["unsettled_usd"]) != sum((money(row["net_usd"]) for row in lots), D("0"))):
        reasons.append("pending_settlement_mismatch")
    if incomplete_fees:
        reasons.append("fee_incomplete")
    reasons = sorted(set(reasons))
    return {
        "entry_intent_id": intent["intent_id"], "instrument_id": instrument,
        "verified_quantity": quantity, "committed_sell_quantity": committed_sell,
        "incurred_exit_fees_usd": str(sell_fees_final),
        "outstanding_exit_fees_usd": str(
            money(proposal["exit_fee_usd"]) if incomplete_fees else
            (max(money(proposal["exit_fee_usd"]) - sell_fees_final, D("0")) if quantity else D("0"))),
        "orders": [orders[key] for key in sorted(orders)],
        "executions": [executions[key] for key in sorted(executions)],
        "commissions": [commissions_by_id[key] for key in sorted(commissions_by_id)],
        "pending_lots": lots, "reasons": reasons, "settled_cash_usd": str(expected_cash),
        "incomplete_fees": incomplete_fees, "proposal": proposal,
    }


def _account_effect(connection, snapshot, derived, prior_version):
    basis = _basis_adjustment(connection, prior_version)
    proposal = derived["proposal"]
    remaining_buy = sum(order["original_quantity"] - order["cumulative_executed_quantity"]
                        for order in derived["orders"]
                        if order["side"] == "buy" and order["state"] in ("working", "unknown"))
    entry_execution_ids = {row["execution_id"] for row in derived["executions"]
                           if row["side"] == "buy"}
    entry_fees = sum((money(row["amount_usd"]) for row in derived["commissions"]
                      if row["execution_id"] in entry_execution_ids), D("0"))
    reserve = D(remaining_buy) * (money(proposal["limit_price_usd"])
                                  + money(proposal["slippage_usd_per_share"]))
    final_entry_ids = {row["execution_id"] for row in derived["commissions"] if row["final"]}
    if remaining_buy or not entry_execution_ids <= final_entry_ids:
        reserve += max(money(proposal["entry_fee_usd"]) - entry_fees, D("0"))
    reserve += money(derived["outstanding_exit_fees_usd"])
    retain_risk = (derived["verified_quantity"] > 0 or remaining_buy > 0
                   or derived["incomplete_fees"])
    mark = store._mark(snapshot["mark"])
    account = store._parse_state(connection.execute(
        "SELECT payload FROM account_state WHERE id=1").fetchone()[0])
    assessment = assess(mark, store._mark(account["session_start"]),
                        store._mark(account["week_start"]), tuple(basis["halt_reasons"]))
    intent = store._record_payload(connection.execute(
        "SELECT payload FROM intents WHERE intent_id=?", (derived["entry_intent_id"],)).fetchone()[0])
    return {
        "reconciliation_id": snapshot["reconciliation_id"],
        "snapshot_id": snapshot["snapshot_id"], "intent_id": derived["entry_intent_id"],
        "at": utc(snapshot["at"]).isoformat(), "settled_cash_usd": derived["settled_cash_usd"],
        "position_quantity": derived["verified_quantity"], "mark": store._mark_payload(mark),
        "halt_reasons": list(assessment.halt_reasons), "reserved_cash_usd": str(reserve),
        "reserved_exposure_gbp": intent["reservation"]["exposure_gbp"] if retain_risk else "0",
        "reserved_loss_gbp": intent["reservation"]["planned_loss_gbp"] if retain_risk else "0",
        "committed_version": prior_version + 1,
    }


def _state_payload(raw):
    value = store.decode(raw)
    required = {
        "schema", "version", "account_id", "environment", "as_of", "status",
        "last_snapshot_id", "account_version", "entry_intent_id", "instrument_id",
        "verified_quantity", "committed_sell_quantity", "incurred_exit_fees_usd",
        "outstanding_exit_fees_usd", "unresolved_reasons", "orders", "executions",
        "commissions", "pending_lots", "live_trading_enabled",
    }
    if (not isinstance(value, dict) or set(value) != required or value["schema"] != STATE_SCHEMA
            or value["environment"] != "synthetic" or value["live_trading_enabled"] is not False):
        raise ValueError("Invalid reducing reconciliation state")
    store._version(value["version"], "reducing reconciliation version")
    store._version(value["account_version"], "reducing reconciliation account version")
    store._identity(value["account_id"], "reducing reconciliation account")
    store._timestamp_string(value["as_of"], "reducing reconciliation state time")
    if value["last_snapshot_id"] is not None:
        store._identity(value["last_snapshot_id"], "reducing reconciliation snapshot")
    for field in ("entry_intent_id", "instrument_id"):
        if value[field] is not None:
            store._identity(value[field], field.replace("_", " "))
    if value["status"] not in ("reconciled", "unresolved"):
        raise ValueError("Invalid reducing reconciliation status")
    if (not isinstance(value["unresolved_reasons"], list)
            or value["unresolved_reasons"] != sorted(set(value["unresolved_reasons"]))
            or (value["status"] == "reconciled") != (not value["unresolved_reasons"])):
        raise ValueError("Invalid reducing reconciliation reasons")
    for field in ("verified_quantity", "committed_sell_quantity"):
        if type(value[field]) is not int or value[field] < 0:
            raise ValueError("Invalid reducing reconciliation quantity")
    for field in ("incurred_exit_fees_usd", "outstanding_exit_fees_usd"):
        store._decimal_string(value[field], field.replace("_", " "))
    for row in value["orders"]:
        _order(row)
    for row in value["executions"]:
        _execution(row)
    for row in value["commissions"]:
        _commission(row)
    for row in value["pending_lots"]:
        _pending(row)
    return value


def _report(state):
    return {
        "schema": REPORT_SCHEMA, "mode": MODE, "account_id": state["account_id"],
        "environment": state["environment"], "version": state["version"],
        "as_of": state["as_of"], "status": state["status"],
        "last_snapshot_id": state["last_snapshot_id"], "account_version": state["account_version"],
        "entry_intent_id": state["entry_intent_id"], "instrument_id": state["instrument_id"],
        "verified_quantity": state["verified_quantity"],
        "committed_sell_quantity": state["committed_sell_quantity"],
        "available_sell_quantity": (state["verified_quantity"] - state["committed_sell_quantity"]
                                    if not state["unresolved_reasons"] else None),
        "incurred_exit_fees_usd": state["incurred_exit_fees_usd"],
        "outstanding_exit_fees_usd": state["outstanding_exit_fees_usd"],
        "unresolved_reasons": state["unresolved_reasons"],
        "orders": deepcopy(state["orders"]), "executions": deepcopy(state["executions"]),
        "commissions": deepcopy(state["commissions"]),
        "pending_lots": deepcopy(state["pending_lots"]),
        "settlement_release_enabled": False, "dispatch_authorized": False,
        "live_trading_enabled": False,
    }


def _read(connection):
    if connection.execute("PRAGMA user_version").fetchone()[0] != store.REDUCING_DATABASE_VERSION:
        raise ValueError("Reducing reconciliation requires a fresh v4 order database")
    row = connection.execute("SELECT payload FROM reducing_reconciliation_state WHERE id=1").fetchone()
    if row is None:
        raise ValueError("Reducing reconciliation state missing; fresh v4 initialization required")
    stored = _state_payload(row[0])
    baseline = order_allocations._baseline(connection)
    if stored["account_id"] != baseline["account_id"]:
        raise ValueError("Reducing reconciliation baseline account mismatch")
    initial_at = baseline["at"]
    projected = _state_payload(store.pack({
        **stored, "version": 0, "as_of": initial_at, "status": "reconciled",
        "last_snapshot_id": None, "account_version": 0, "entry_intent_id": None,
        "instrument_id": None, "verified_quantity": 0, "committed_sell_quantity": 0,
        "incurred_exit_fees_usd": "0", "outstanding_exit_fees_usd": "0",
        "unresolved_reasons": [], "orders": [], "executions": [], "commissions": [],
        "pending_lots": [],
    }))
    events = []
    seen_inputs, seen_snapshots, seen_reconciliations = set(), set(), set()
    seen_reconciliations.update(_entry_reconciliation_ids(connection))
    _, _, writer_events = order_writer._read_writer(connection)
    last_writer_version = 0
    last_at = utc(initial_at)
    for expected, (sequence, event_id, kind, input_sha, payload_sha, raw) in enumerate(
            connection.execute("SELECT sequence,event_id,kind,input_sha256,payload_sha256,payload "
                               "FROM reducing_reconciliation_events ORDER BY sequence"), 1):
        event = store.decode(raw)
        if (sequence != expected or kind not in ("snapshot_applied", "snapshot_unresolved", "incident")
                or not isinstance(event, dict) or set(event) != {
                    "schema", "event_id", "kind", "at", "committed_version", "input_sha256",
                    "prior_account_version", "writer_evidence_sha256",
                    "allocation_evidence_sha256", "account_adjustment_sha256", "reasons", "state"}
                or event["schema"] != EVENT_SCHEMA or event["event_id"] != event_id
                or event["kind"] != kind or event["committed_version"] != sequence
                or event["input_sha256"] != input_sha or store.digest(event) != payload_sha):
            raise ValueError("Invalid reducing reconciliation event")
        if (not isinstance(event["reasons"], list)
                or event["reasons"] != sorted(set(event["reasons"]))
                or event["reasons"] != event["state"]["unresolved_reasons"]):
            raise ValueError("Invalid reducing reconciliation event reasons")
        base = {key: value for key, value in event.items() if key != "event_id"}
        if event_id != store.digest(base):
            raise ValueError("Reducing reconciliation event identity mismatch")
        event_at = store._timestamp_string(event["at"], "reducing reconciliation event time")
        if event_at < last_at:
            raise ValueError("Reducing reconciliation event time moved backwards")
        inbox = connection.execute(
            "SELECT receipt_id,payload_sha256,payload,snapshot_id,reconciliation_id "
            "FROM reducing_reconciliation_inbox "
            "WHERE payload_sha256=?", (input_sha,)).fetchone()
        if inbox is None or inbox[0] != input_sha or inbox[1] != input_sha:
            raise ValueError("Reducing reconciliation retained input is missing")
        snapshot = _snapshot(store.decode(inbox[2]))
        if (store.digest(snapshot) != input_sha or input_sha in seen_inputs
                or (snapshot["snapshot_id"], snapshot["reconciliation_id"]) != inbox[3:]):
            raise ValueError("Reducing reconciliation retained input binding mismatch")
        identity_reason = ("snapshot_identity_conflict" if snapshot["snapshot_id"] in seen_snapshots
                           else "reconciliation_identity_conflict"
                           if snapshot["reconciliation_id"] in seen_reconciliations else None)
        identity_incident = identity_reason is not None
        if not identity_incident and (
                snapshot["expected_reducing_reconciliation_version"] != sequence - 1
                or snapshot["expected_account_version"] != event["prior_account_version"]
                or snapshot["account_id"] != stored["account_id"]
                or utc(snapshot["at"]) != event_at):
            raise ValueError("Reducing reconciliation event expected versions disagree")
        if identity_incident:
            if event["writer_evidence_sha256"] is not None or event["allocation_evidence_sha256"] is not None:
                raise ValueError("Identity incident unexpectedly claims current authority")
            if event_at < utc(snapshot["at"]):
                raise ValueError("Identity incident precedes its source time")
        else:
            _, allocation_records, allocation_incidents = order_allocations._read(connection)
            allocation_history = sorted(allocation_records + allocation_incidents,
                                        key=lambda row: row["committed_version"])
            wv = snapshot["expected_writer_version"]
            av = snapshot["expected_allocation_version"]
            if (not 0 < wv <= len(writer_events) or not 0 < av <= len(allocation_history)
                    or store.digest(writer_events[wv - 1]) != event["writer_evidence_sha256"]
                    or store.digest(allocation_history[av - 1]) != event["allocation_evidence_sha256"]
                    or event_at < utc(writer_events[wv - 1]["at"])):
                raise ValueError("Reducing reconciliation authority evidence mismatch")
            if store._periods(snapshot["at"]) != (baseline["session"], baseline["week"]):
                raise ValueError("Reducing reconciliation account time binding mismatch")
        derived = ({"reasons": []} if identity_incident
                   else _derive(connection, snapshot, projected))
        durable = sorted(set(derived["reasons"]) & DURABLE_REASONS)
        if identity_incident:
            expected_kind = "incident"
            expected_reasons = sorted(set(projected["unresolved_reasons"] + [identity_reason]))
        elif durable or set(projected["unresolved_reasons"]) & DURABLE_REASONS:
            expected_kind = "incident"
            expected_reasons = sorted(set(projected["unresolved_reasons"] + durable))
        else:
            expected_kind = ("snapshot_unresolved" if set(derived["reasons"]) - {"fee_incomplete"}
                             else "snapshot_applied")
            expected_reasons = derived["reasons"]
        if (kind, event["reasons"]) != (expected_kind, expected_reasons):
            raise ValueError("Reducing reconciliation outcome disagrees with replay")
        reasons = event["reasons"]
        clear = ([] if kind == "incident" else
                 sorted(set(projected["unresolved_reasons"]) & TRANSIENT_REASONS))
        expected_request = order_reconciliation._writer_reconciliation_request(
            snapshot["reconciliation_id"], event_at, clear, reasons)
        candidates = (writer_events[last_writer_version:] if identity_incident
                      else writer_events[wv:wv + 1])
        disarm = next((item for item in candidates
                       if item["kind"] == "reconciliation_disarmed"
                       and item["request"] == expected_request and utc(item["at"]) == event_at
                       and item["committed_version"] > last_writer_version), None)
        if disarm is None:
            raise ValueError("Reducing reconciliation writer disarm binding mismatch")
        last_writer_version = disarm["committed_version"]
        expected_state = deepcopy(projected)
        expected_state.update(
            version=sequence, as_of=event["at"], status="unresolved" if reasons else "reconciled",
            last_snapshot_id=snapshot["snapshot_id"], unresolved_reasons=reasons)
        if kind == "snapshot_applied":
            if event_at < utc(_basis_adjustment(connection, event["prior_account_version"])["at"]):
                raise ValueError("Reducing reconciliation predates its account basis")
            expected_state.update({key: derived[key] for key in (
                "entry_intent_id", "instrument_id", "verified_quantity",
                "committed_sell_quantity", "incurred_exit_fees_usd",
                "outstanding_exit_fees_usd", "orders", "executions", "commissions", "pending_lots")})
            expected_state["account_version"] = event["prior_account_version"] + 1
            adjustment = connection.execute(
                "SELECT payload FROM reconciliation_adjustments WHERE committed_version=?",
                (expected_state["account_version"],)).fetchone()
            expected_adjustment = _account_effect(
                connection, snapshot, derived, event["prior_account_version"])
            if (adjustment is None or store._adjustment_payload(adjustment[0]) != expected_adjustment
                    or store.digest(expected_adjustment) != event["account_adjustment_sha256"]):
                raise ValueError("Reducing reconciliation account adjustment is missing")
        elif event["account_adjustment_sha256"] is not None:
            raise ValueError("Reducing reconciliation incident changed the account")
        if _state_payload(store.pack(event["state"])) != expected_state:
            raise ValueError("Reducing reconciliation state disagrees with retained input replay")
        projected = expected_state
        events.append(event)
        last_at = event_at
        seen_inputs.add(input_sha)
        seen_snapshots.add(snapshot["snapshot_id"])
        seen_reconciliations.add(snapshot["reconciliation_id"])
    if len(seen_inputs) != connection.execute(
            "SELECT COUNT(*) FROM reducing_reconciliation_inbox").fetchone()[0]:
        raise ValueError("Reducing reconciliation inbox contains unaudited evidence")
    if stored != projected:
        raise ValueError("Reducing reconciliation projection disagrees with event history")
    return stored, events


def status(path):
    with store.database(path) as connection:
        store._read_state(connection)
        return _report(_read(connection)[0])


def history(path):
    with store.database(path) as connection:
        store._read_state(connection)
        return _read(connection)[1]


def _append(connection, kind, at, input_sha, prior_account_version, writer_sha,
            allocation_sha, adjustment_sha, state):
    state = deepcopy(state)
    version = state["version"] + 1
    state.update(version=version, as_of=at.isoformat())
    base = {
        "schema": EVENT_SCHEMA, "kind": kind, "at": at.isoformat(),
        "committed_version": version, "input_sha256": input_sha,
        "prior_account_version": prior_account_version,
        "writer_evidence_sha256": writer_sha, "allocation_evidence_sha256": allocation_sha,
        "account_adjustment_sha256": adjustment_sha,
        "reasons": state["unresolved_reasons"], "state": state,
    }
    event = {**base, "event_id": store.digest(base)}
    connection.execute("INSERT INTO reducing_reconciliation_events VALUES (?, ?, ?, ?, ?, ?)",
                       (version, event["event_id"], kind, input_sha, store.digest(event), store.pack(event)))
    connection.execute("UPDATE reducing_reconciliation_state SET payload=? WHERE id=1",
                       (store.pack(state),))
    return state, event


def apply(path, raw):
    snapshot = _snapshot(raw)
    input_sha = store.digest(snapshot)
    with store.database(path, write=True) as connection:
        account = store._read_state(connection)
        writer, _, writer_events = order_writer._read_writer(connection)
        allocation, allocation_records, allocation_incidents = order_allocations._read(connection)
        state, events = _read(connection)
        existing_rows = connection.execute(
            "SELECT payload_sha256,payload FROM reducing_reconciliation_inbox WHERE snapshot_id=?",
            (snapshot["snapshot_id"],)).fetchall()
        exact = next((row for row in existing_rows
                      if row[0] == input_sha and store.decode(row[1]) == snapshot), None)
        if exact is not None:
            result = _report(state)
            result.update(outcome=state["status"], duplicate=True)
            return result
        if existing_rows:
            reasons = ["snapshot_identity_conflict"]
        elif connection.execute(
                "SELECT 1 FROM reducing_reconciliation_inbox WHERE reconciliation_id=?",
                (snapshot["reconciliation_id"],)).fetchone() or (
                snapshot["reconciliation_id"] in _entry_reconciliation_ids(connection)):
            reasons = ["reconciliation_identity_conflict"]
        else:
            reasons = []
        if (not reasons and snapshot["account_id"] != account["account_id"]
                or state["account_id"] != account["account_id"]):
            raise ValueError("Reducing reconciliation account mismatch")
        if not reasons:
            for field, actual in (
                    ("expected_reducing_reconciliation_version", state["version"]),
                    ("expected_account_version", account["version"]),
                    ("expected_writer_version", writer["version"]),
                    ("expected_allocation_version", allocation["version"])):
                if snapshot[field] != actual:
                    raise ValueError(field.replace("expected_", "").replace("_", " ") + " changed")
            if not snapshot["expected_writer_version"] or not snapshot["expected_allocation_version"]:
                raise ValueError("Reducing reconciliation authority evidence is unavailable")
            writer_sha = store.digest(writer_events[snapshot["expected_writer_version"] - 1])
            allocation_history = sorted(allocation_records + allocation_incidents,
                                        key=lambda row: row["committed_version"])
            allocation_sha = store.digest(
                allocation_history[snapshot["expected_allocation_version"] - 1])
        else:
            writer_sha = allocation_sha = None
        source_at = utc(snapshot["at"])
        at = (max(source_at, utc(state["as_of"]), utc(account["at"]),
                  utc(writer_events[-1]["at"])) if reasons and writer_events else
              max(source_at, utc(state["as_of"]), utc(account["at"])) if reasons else source_at)
        if not reasons and (at < utc(state["as_of"]) or at < utc(account["at"])
                            or (writer_events and at < utc(writer_events[-1]["at"]))):
            raise ValueError("Reducing reconciliation time moved backwards")
        if not reasons and store._periods(snapshot["at"]) != (account["session"], account["week"]):
            raise ValueError("Reducing reconciliation requires a reviewed period transition")
        connection.execute("INSERT INTO reducing_reconciliation_inbox VALUES (?, ?, ?, ?, ?)",
                           (input_sha, snapshot["snapshot_id"], snapshot["reconciliation_id"], input_sha,
                            store.pack(snapshot)))
        if reasons:
            state.update(status="unresolved", last_snapshot_id=snapshot["snapshot_id"],
                         unresolved_reasons=sorted(set(state["unresolved_reasons"] + reasons)))
            state, event = _append(connection, "incident", at, input_sha, account["version"],
                                   None, None, None, state)
            order_reconciliation._disarm(connection, snapshot["reconciliation_id"], at,
                                          state["unresolved_reasons"], [])
            result = _report(state)
            result.update(outcome="unresolved", duplicate=False, event=event)
            return result
        derived = _derive(connection, snapshot, state)
        durable = sorted(set(derived["reasons"]) & DURABLE_REASONS)
        latched = sorted(set(state["unresolved_reasons"]) &
                         (DURABLE_REASONS |
                          {"snapshot_identity_conflict", "reconciliation_identity_conflict"}))
        if durable or latched:
            state.update(status="unresolved", last_snapshot_id=snapshot["snapshot_id"],
                         unresolved_reasons=sorted(set(state["unresolved_reasons"] + durable)))
            state, event = _append(connection, "incident", at, input_sha, account["version"],
                                   writer_sha, allocation_sha, None, state)
            order_reconciliation._disarm(connection, snapshot["reconciliation_id"], at,
                                          state["unresolved_reasons"], [])
            result = _report(state)
            result.update(outcome="unresolved", duplicate=False, event=event)
            return result
        blocking_transient = sorted(set(derived["reasons"]) - {"fee_incomplete"})
        if blocking_transient:
            prior_reasons = state["unresolved_reasons"]
            state.update(status="unresolved", last_snapshot_id=snapshot["snapshot_id"],
                         unresolved_reasons=derived["reasons"])
            state, event = _append(connection, "snapshot_unresolved", at, input_sha,
                                   account["version"], writer_sha, allocation_sha, None, state)
            order_reconciliation._disarm(connection, snapshot["reconciliation_id"], at,
                                          derived["reasons"],
                                          sorted(set(prior_reasons) & TRANSIENT_REASONS))
            result = _report(state)
            result.update(outcome="unresolved", duplicate=False, event=event)
            return result
        adjustment = _account_effect(connection, snapshot, derived, account["version"])
        version = adjustment["committed_version"]
        connection.execute("INSERT INTO reconciliation_adjustments VALUES (?, ?, ?)",
                           (adjustment["reconciliation_id"], version, store.pack(adjustment)))
        connection.execute("INSERT INTO audit VALUES (?, 'reconciliation', ?, ?)",
                           (version, adjustment["reconciliation_id"], store.digest(adjustment)))
        account.update(version=version, at=adjustment["at"],
                       settled_cash_usd=adjustment["settled_cash_usd"],
                       position_quantity=adjustment["position_quantity"], mark=adjustment["mark"],
                       halt_reasons=adjustment["halt_reasons"],
                       reserved_cash_usd=adjustment["reserved_cash_usd"],
                       reserved_exposure_gbp=adjustment["reserved_exposure_gbp"],
                       reserved_loss_gbp=adjustment["reserved_loss_gbp"])
        store._write_state(connection, account)
        unresolved = derived["reasons"]
        prior_reasons = state["unresolved_reasons"]
        state.update(
            status="unresolved" if unresolved else "reconciled",
            last_snapshot_id=snapshot["snapshot_id"], account_version=version,
            unresolved_reasons=unresolved,
            **{key: derived[key] for key in (
                "entry_intent_id", "instrument_id", "verified_quantity",
                "committed_sell_quantity", "incurred_exit_fees_usd",
                "outstanding_exit_fees_usd", "orders", "executions", "commissions", "pending_lots")})
        state, event = _append(connection, "snapshot_applied", at, input_sha, version - 1,
                               writer_sha, allocation_sha, store.digest(adjustment), state)
        order_reconciliation._disarm(connection, snapshot["reconciliation_id"], at,
                                      unresolved, sorted(set(prior_reasons) & TRANSIENT_REASONS))
        result = _report(state)
        result.update(outcome=state["status"], duplicate=False, adjustment=adjustment, event=event)
        return result
