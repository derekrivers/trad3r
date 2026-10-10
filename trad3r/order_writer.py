"""Fenced single writer and deterministic synthetic submission adapter."""
from copy import deepcopy
from dataclasses import dataclass

from .data import decode
from .ledger import utc
from . import order_store as store


WRITER_SCHEMA = "order-writer-state-v1"
CLAIM_SCHEMA = "order-writer-claim-v1"
SUBMISSION_SCHEMA = "order-submission-operation-v1"
RECOVERY_SCHEMA = "order-writer-recovery-v1"
EVENT_SCHEMA = "order-writer-event-v1"
RECORD_SCHEMA = "order-submission-v1"
MODE = "synthetic_single_writer_only"

CLAIM_FIELDS = {"schema", "claim_id", "owner_id", "at", "expected_epoch"}
SUBMISSION_FIELDS = {
    "schema", "operation_id", "intent_id", "owner_id", "epoch", "at",
    "expected_account_version",
}
RECOVERY_FIELDS = {"schema", "recovery_id", "owner_id", "epoch", "at"}
WRITER_FIELDS = {
    "schema", "version", "epoch", "owner_id", "claim_id", "claimed_at",
    "disarmed", "unresolved_reasons", "live_trading_enabled",
}
RECORD_FIELDS = {
    "schema", "operation_id", "intent_id", "client_order_id", "request",
    "request_sha256", "command", "command_sha256", "state", "broker_order_id",
    "reason", "marked_at", "resolved_at", "owner_id", "epoch",
    "last_event_version",
}
EVENT_FIELDS = {
    "schema", "event_id", "kind", "at", "committed_version", "request",
    "writer", "submission",
}
EVENT_KINDS = {
    "writer_claimed", "submission_marked", "submission_result",
    "submission_expired", "writer_recovered", "writer_incident",
    "reconciliation_disarmed", "reconciliation_applied",
}
SYNTHETIC_OUTCOMES = {"acknowledged", "rejected", "accept_then_timeout"}


class SubmissionUncertain(RuntimeError):
    """The synthetic adapter accepted a command but withheld its acknowledgement."""


@dataclass
class SyntheticAdapter:
    calls: int = 0

    def submit(self, command, outcome):
        self.calls += 1
        if outcome == "acknowledged":
            return {
                "outcome": "acknowledged",
                "broker_order_id": "synthetic-" + store.digest(command)[:24],
            }
        if outcome == "rejected":
            return {"outcome": "rejected", "reason": "synthetic_rejection"}
        if outcome == "accept_then_timeout":
            raise SubmissionUncertain("synthetic acknowledgement lost")
        raise ValueError("Unsupported synthetic adapter outcome")


def _writer_payload(raw):
    value = decode(raw) if not isinstance(raw, dict) else deepcopy(raw)
    if not isinstance(value, dict) or set(value) != WRITER_FIELDS or value["schema"] != WRITER_SCHEMA:
        raise ValueError("Invalid stored writer state")
    store._version(value["version"], "writer version")
    store._version(value["epoch"], "writer epoch")
    for field in ("owner_id", "claim_id"):
        if value[field] is not None:
            store._identity(value[field], field.replace("_", " "))
    if (value["owner_id"] is None) != (value["claim_id"] is None):
        raise ValueError("Writer owner and claim must be set together")
    if value["claimed_at"] is not None:
        store._timestamp_string(value["claimed_at"], "writer claim time")
    if (value["owner_id"] is None) != (value["claimed_at"] is None):
        raise ValueError("Writer claim time disagrees with ownership")
    if type(value["disarmed"]) is not bool or value["live_trading_enabled"] is not False:
        raise ValueError("Writer is not safely disarmed from live trading")
    reasons = value["unresolved_reasons"]
    if not isinstance(reasons, list) or reasons != sorted(set(reasons)):
        raise ValueError("Invalid writer unresolved reasons")
    if reasons and not value["disarmed"]:
        raise ValueError("Writer with unresolved reasons must be disarmed")
    if value["owner_id"] is None and not value["disarmed"]:
        raise ValueError("Unowned writer must be disarmed")
    return value


def _submission_payload(raw):
    value = decode(raw) if not isinstance(raw, dict) else deepcopy(raw)
    if not isinstance(value, dict) or set(value) != RECORD_FIELDS or value["schema"] != RECORD_SCHEMA:
        raise ValueError("Invalid stored submission")
    for field in ("operation_id", "intent_id", "client_order_id", "owner_id"):
        store._identity(value[field], field.replace("_", " "))
    store._version(value["epoch"], "submission epoch")
    store._version(value["last_event_version"], "submission event version")
    request = _request(value["request"], SUBMISSION_FIELDS, SUBMISSION_SCHEMA)
    if (request["operation_id"], request["intent_id"], request["owner_id"], request["epoch"]) != (
            value["operation_id"], value["intent_id"], value["owner_id"], value["epoch"]):
        raise ValueError("Stored submission request identities disagree")
    if value["request_sha256"] != store.digest(value["request"]):
        raise ValueError("Stored submission request digest mismatch")
    if value["command_sha256"] != store.digest(value["command"]):
        raise ValueError("Stored submission command digest mismatch")
    if value["state"] not in (
            "submitting", "unknown", "acknowledged", "partially_filled", "filled",
            "rejected", "cancelled"):
        raise ValueError("Invalid stored submission state")
    store._timestamp_string(value["marked_at"], "submission marker time")
    if value["resolved_at"] is not None:
        store._timestamp_string(value["resolved_at"], "submission resolution time")
    if value["state"] == "submitting" and (value["resolved_at"] is not None or value["reason"] is not None):
        raise ValueError("Submitting operation cannot have a resolution")
    if value["broker_order_id"] is not None:
        store._identity(value["broker_order_id"], "broker order id")
    if value["state"] in ("acknowledged", "partially_filled", "filled"):
        if value["broker_order_id"] is None or value["reason"] is not None or value["resolved_at"] is None:
            raise ValueError("Invalid confirmed submission")
    if value["state"] in ("unknown", "rejected", "cancelled"):
        if not isinstance(value["reason"], str) or value["resolved_at"] is None:
            raise ValueError("Resolved submission requires a reason and time")
    return value


def _request(value, fields, schema):
    if not isinstance(value, dict) or set(value) != fields or value["schema"] != schema:
        raise ValueError(f"Input fields do not match {schema}")
    if schema == CLAIM_SCHEMA:
        store._identity(value["claim_id"], "claim id")
        store._identity(value["owner_id"], "owner id")
        store._timestamp_string(value["at"], "claim time")
        store._version(value["expected_epoch"], "expected epoch")
    elif schema == SUBMISSION_SCHEMA:
        store._identity(value["operation_id"], "operation id")
        store._identity(value["intent_id"], "intent id")
        store._identity(value["owner_id"], "owner id")
        store._timestamp_string(value["at"], "submission time")
        store._version(value["epoch"], "writer epoch")
        store._version(value["expected_account_version"], "expected account version")
    elif schema == RECOVERY_SCHEMA:
        store._identity(value["recovery_id"], "recovery id")
        store._identity(value["owner_id"], "owner id")
        store._timestamp_string(value["at"], "recovery time")
        store._version(value["epoch"], "writer epoch")
    return deepcopy(value)


def _event(kind, at, version, request, writer, submission=None):
    event_at = at.isoformat() if hasattr(at, "isoformat") else utc(at).isoformat()
    base = {
        "schema": EVENT_SCHEMA, "kind": kind, "at": event_at,
        "committed_version": version, "request": request,
        "writer": writer, "submission": submission,
    }
    return dict(base, event_id=store.digest(base))


def _append_event(connection, kind, at, request, writer, submission=None):
    writer = deepcopy(writer)
    writer["version"] += 1
    if submission is not None:
        submission = deepcopy(submission)
        submission["last_event_version"] = writer["version"]
    event = _event(kind, at, writer["version"], request, writer, submission)
    connection.execute(
        "INSERT INTO writer_events VALUES (?, ?, ?, ?, ?)",
        (writer["version"], event["event_id"], kind, store.digest(event), store.pack(event)),
    )
    connection.execute("UPDATE writer_state SET payload=? WHERE id=1", (store.pack(writer),))
    if submission is not None:
        connection.execute(
            "INSERT INTO submissions VALUES (?, ?, ?, ?, ?) "
            "ON CONFLICT(operation_id) DO UPDATE SET broker_order_id=excluded.broker_order_id,payload=excluded.payload",
            (submission["operation_id"], submission["intent_id"], submission["client_order_id"],
             submission["broker_order_id"], store.pack(submission)),
        )
    return writer, submission, event


def _read_writer(connection):
    if connection.execute("PRAGMA user_version").fetchone()[0] not in (2, 3):
        raise ValueError("Order database requires an explicit P4.3 writer migration")
    row = connection.execute("SELECT payload FROM writer_state WHERE id=1").fetchone()
    if row is None:
        raise ValueError("Writer state missing; explicit recovery required")
    projected_writer = {
        "schema": WRITER_SCHEMA, "version": 0, "epoch": 0, "owner_id": None,
        "claim_id": None, "claimed_at": None, "disarmed": True,
        "unresolved_reasons": [], "live_trading_enabled": False,
    }
    projected_submissions = {}
    events = []
    last_at = None
    for expected, (sequence, event_id, kind, payload_sha, raw) in enumerate(connection.execute(
            "SELECT sequence,event_id,kind,payload_sha256,payload FROM writer_events ORDER BY sequence"), 1):
        event = decode(raw)
        if (sequence != expected or kind not in EVENT_KINDS or not isinstance(event, dict)
                or set(event) != EVENT_FIELDS or event["schema"] != EVENT_SCHEMA
                or event["event_id"] != event_id or event["kind"] != kind
                or event["committed_version"] != sequence or store.digest(event) != payload_sha):
            raise ValueError("Invalid writer event sequence or payload")
        base = {key: value for key, value in event.items() if key != "event_id"}
        if event_id != store.digest(base):
            raise ValueError("Writer event identity mismatch")
        event_at = store._timestamp_string(event["at"], "writer event time")
        if last_at is not None and event_at < last_at:
            raise ValueError("Writer event time moved backwards")
        last_at = event_at
        current_writer = _writer_payload(event["writer"])
        if current_writer["version"] != sequence:
            raise ValueError("Writer event version mismatch")
        submission = None if event["submission"] is None else _submission_payload(event["submission"])
        prior = projected_writer
        expected_writer = deepcopy(prior)
        expected_writer["version"] = sequence
        if kind == "writer_claimed":
            request = _request(event["request"], CLAIM_FIELDS, CLAIM_SCHEMA)
            if event["at"] != utc(request["at"]).isoformat():
                raise ValueError("Writer claim event time disagrees with its request")
            if (submission is not None or prior["owner_id"] is not None or prior["unresolved_reasons"]
                    or request["expected_epoch"] != prior["epoch"]):
                raise ValueError("Invalid writer claim transition")
            expected_writer.update(
                epoch=prior["epoch"] + 1, owner_id=request["owner_id"],
                claim_id=request["claim_id"], claimed_at=utc(request["at"]).isoformat(),
                disarmed=False, unresolved_reasons=[])
        elif kind == "writer_recovered":
            request = _request(event["request"], RECOVERY_FIELDS, RECOVERY_SCHEMA)
            if event["at"] != utc(request["at"]).isoformat():
                raise ValueError("Writer recovery event time disagrees with its request")
            if (prior["owner_id"], prior["epoch"]) != (request["owner_id"], request["epoch"]):
                raise ValueError("Invalid writer recovery transition")
            inflight = [record for record in projected_submissions.values()
                        if record["state"] == "submitting"]
            if len(inflight) > 1 or bool(inflight) != (submission is not None):
                raise ValueError("Recovery submission set is inconsistent")
            if submission is not None:
                previous = inflight[0]
                changed = deepcopy(previous)
                changed.update(state="unknown", reason="restart_during_submission",
                               resolved_at=event["at"], last_event_version=sequence)
                if submission != changed:
                    raise ValueError("Invalid recovery submission transition")
                expected_writer["unresolved_reasons"] = sorted(set(
                    prior["unresolved_reasons"] + ["submission_unknown"]))
            expected_writer.update(owner_id=None, claim_id=None, claimed_at=None, disarmed=True)
        elif kind in ("submission_marked", "submission_expired"):
            request = _request(event["request"], SUBMISSION_FIELDS, SUBMISSION_SCHEMA)
            if event["at"] != utc(request["at"]).isoformat():
                raise ValueError("Submission event time disagrees with its request")
            if submission is None or submission["operation_id"] in projected_submissions:
                raise ValueError("Invalid new submission event")
            expected_state = "submitting" if kind == "submission_marked" else "cancelled"
            if (submission["state"] != expected_state or submission["request"] != request
                    or prior["disarmed"] or prior["unresolved_reasons"]
                    or submission["marked_at"] != event["at"]
                    or (submission["owner_id"], submission["epoch"]) != (
                        prior["owner_id"], prior["epoch"])):
                raise ValueError("Submission marker state mismatch")
            if kind == "submission_expired" and (
                    submission["reason"] != "expired_authority"
                    or submission["resolved_at"] != event["at"]):
                raise ValueError("Expired submission tombstone is inconsistent")
        elif kind == "submission_result":
            previous = projected_submissions.get(submission["operation_id"] if submission else None)
            if previous is None or previous["state"] != "submitting" or submission["state"] == "submitting":
                raise ValueError("Invalid submission result transition")
            expected_result = {"outcome": submission["state"]}
            if submission["state"] == "acknowledged":
                expected_result["broker_order_id"] = submission["broker_order_id"]
            else:
                expected_result["reason"] = submission["reason"]
            if event["request"] != {
                    "operation_id": submission["operation_id"],
                    "adapter_result": expected_result}:
                raise ValueError("Submission result event disagrees with its projection")
            changed = deepcopy(previous)
            changed.update(state=submission["state"], broker_order_id=submission["broker_order_id"],
                           reason=submission["reason"], resolved_at=submission["resolved_at"],
                           last_event_version=sequence)
            if changed != submission:
                raise ValueError("Submission result changed immutable command fields")
            if submission["state"] in ("unknown", "rejected"):
                reason = "submission_unknown" if submission["state"] == "unknown" else "submission_rejected"
                expected_writer["disarmed"] = True
                expected_writer["unresolved_reasons"] = sorted(set(
                    prior["unresolved_reasons"] + [reason]))
        elif kind == "writer_incident":
            request = _request(event["request"], SUBMISSION_FIELDS, SUBMISSION_SCHEMA)
            if event["at"] != utc(request["at"]).isoformat():
                raise ValueError("Writer incident time disagrees with its request")
            if submission is not None:
                raise ValueError("Writer incident cannot change a submission")
            expected_writer["disarmed"] = True
            expected_writer["unresolved_reasons"] = sorted(set(
                prior["unresolved_reasons"] + ["writer_identity_conflict"]))
        elif kind in ("reconciliation_disarmed", "reconciliation_applied"):
            request = event["request"]
            if (not isinstance(request, dict) or set(request) != {
                    "schema", "reconciliation_id", "at", "clear_reasons", "add_reasons"}
                    or request["schema"] != "writer-reconciliation-v1"
                    or event["at"] != utc(request["at"]).isoformat()
                    or not isinstance(request["clear_reasons"], list)
                    or not isinstance(request["add_reasons"], list)
                    or request["clear_reasons"] != sorted(set(request["clear_reasons"]))
                    or request["add_reasons"] != sorted(set(request["add_reasons"]))
                    or not all(isinstance(reason, str) and reason
                               for reason in request["clear_reasons"] + request["add_reasons"])):
                raise ValueError("Invalid writer reconciliation event")
            store._identity(request["reconciliation_id"], "writer reconciliation id")
            expected_writer.update(owner_id=None, claim_id=None, claimed_at=None, disarmed=True)
            expected_writer["unresolved_reasons"] = sorted(
                (set(prior["unresolved_reasons"]) - set(request["clear_reasons"]))
                | set(request["add_reasons"]))
            if kind == "reconciliation_disarmed" and submission is not None:
                raise ValueError("Reconciliation invalidation cannot change an order")
            if kind == "reconciliation_applied" and submission is not None:
                previous = projected_submissions.get(submission["operation_id"])
                if previous is None:
                    raise ValueError("Reconciliation references an unknown submission")
                changed = deepcopy(previous)
                changed.update(state=submission["state"], broker_order_id=submission["broker_order_id"],
                               reason=submission["reason"], resolved_at=submission["resolved_at"],
                               last_event_version=sequence)
                if changed != submission:
                    raise ValueError("Reconciliation changed immutable submission fields")
        if current_writer != expected_writer:
            raise ValueError("Writer projection does not follow its event transition")
        projected_writer = current_writer
        if submission is not None:
            projected_submissions[submission["operation_id"]] = submission
        events.append(event)
    stored_writer = _writer_payload(row[0])
    if stored_writer != projected_writer:
        raise ValueError("Writer state disagrees with its event history")
    stored_submissions = {}
    for operation_id, intent_id, client_order_id, broker_order_id, raw in connection.execute(
            "SELECT operation_id,intent_id,client_order_id,broker_order_id,payload FROM submissions"):
        record = _submission_payload(raw)
        if (operation_id, intent_id, client_order_id, broker_order_id) != (
                record["operation_id"], record["intent_id"], record["client_order_id"],
                record["broker_order_id"]):
            raise ValueError("Submission identity columns disagree with payload")
        intent_row = connection.execute(
            "SELECT payload FROM intents WHERE intent_id=?", (intent_id,)
        ).fetchone()
        if intent_row is None:
            raise ValueError("Submission has no admitted intent")
        intent = store._record_payload(intent_row[0])
        if (intent["state"] != "reserved" or intent["client_order_id"] != client_order_id
                or record["command"] != _command(intent, record["request"])):
            raise ValueError("Submission command disagrees with its admission")
        released = connection.execute(
            "SELECT 1 FROM reservation_releases WHERE intent_id=?", (intent_id,)
        ).fetchone() is not None
        if released != (record["state"] == "cancelled" and record["reason"] == "expired_authority"):
            raise ValueError("Submission state disagrees with reservation release")
        stored_submissions[operation_id] = record
    if stored_submissions != projected_submissions:
        raise ValueError("Submission projection disagrees with writer history")
    if len({row["intent_id"] for row in stored_submissions.values()}) != len(stored_submissions):
        raise ValueError("An intent has more than one submission operation")
    return stored_writer, stored_submissions, events


def _report(connection, writer=None, submissions=None):
    account_state = store._read_state(connection)
    if writer is None or submissions is None:
        writer, submissions, events = _read_writer(connection)
    return {
        "schema": WRITER_SCHEMA, "mode": MODE, "version": writer["version"],
        "epoch": writer["epoch"], "owner_id": writer["owner_id"],
        "claim_id": writer["claim_id"], "claimed_at": writer["claimed_at"],
        "disarmed": writer["disarmed"],
        "dispatch_allowed": (not writer["disarmed"] and not writer["unresolved_reasons"]
                             and not any(row["state"] == "submitting"
                                         for row in submissions.values())),
        "unresolved_reasons": writer["unresolved_reasons"],
        "submissions": [submissions[key] for key in sorted(submissions)],
        "account": store._report(account_state), "live_trading_enabled": False,
    }


def status(path):
    with store.database(path) as connection:
        if connection.execute("PRAGMA user_version").fetchone()[0] >= 3:
            from . import order_reconciliation
            order_reconciliation._read(connection)
        return _report(connection)


def history(path):
    with store.database(path) as connection:
        store._read_state(connection)
        if connection.execute("PRAGMA user_version").fetchone()[0] >= 3:
            from . import order_reconciliation
            order_reconciliation._read(connection)
        _, _, events = _read_writer(connection)
        return events


def _require_monotonic(at, events):
    if events and at < utc(events[-1]["at"]):
        raise ValueError("Writer event time cannot move backwards")


def claim(path, payload):
    payload = _request(payload, CLAIM_FIELDS, CLAIM_SCHEMA)
    claim_id = store._identity(payload["claim_id"], "claim id")
    owner_id = store._identity(payload["owner_id"], "owner id")
    at = store._timestamp_string(payload["at"], "claim time")
    expected_epoch = store._version(payload["expected_epoch"], "expected epoch")
    with store.database(path, write=True) as connection:
        account = store._read_state(connection)
        writer, submissions, events = _read_writer(connection)
        previous = next((event for event in events
                         if event["kind"] == "writer_claimed"
                         and event["request"].get("claim_id") == claim_id), None)
        if previous is not None:
            if previous["request"] != payload:
                raise ValueError("Writer claim identity was reused with changed input")
            result = _report(connection, writer, submissions)
            result.update(outcome="claimed", duplicate=True)
            return result
        if connection.execute("PRAGMA user_version").fetchone()[0] >= 3:
            from . import order_reconciliation
            reconciliation, _ = order_reconciliation._read(connection)
            if reconciliation["status"] != "reconciled":
                raise ValueError("Reconciliation is required before claiming the writer")
        if writer["owner_id"] is not None:
            raise ValueError("Writer is already owned")
        if writer["unresolved_reasons"]:
            raise ValueError("Writer has unresolved submissions and cannot be claimed")
        if expected_epoch != writer["epoch"]:
            raise ValueError("Writer epoch changed; read status before claiming")
        _require_monotonic(at, events)
        if at < utc(account["at"]):
            raise ValueError("Writer claim predates the account snapshot")
        writer.update(epoch=writer["epoch"] + 1, owner_id=owner_id, claim_id=claim_id,
                      claimed_at=at.isoformat(), disarmed=False, unresolved_reasons=[])
        writer, _, _ = _append_event(connection, "writer_claimed", at, payload, writer)
        result = _report(connection, writer, submissions)
        result.update(outcome="claimed", duplicate=False)
        return result


def _command(record, request):
    proposal = record["proposal"]
    return {
        "schema": "synthetic-submit-command-v1",
        "operation_id": request["operation_id"], "writer_epoch": request["epoch"],
        "account_id": proposal["account_id"],
        "environment": "synthetic", "client_order_id": proposal["client_order_id"],
        "instrument_id": proposal["instrument_id"], "symbol": proposal["symbol"],
        "currency": proposal["currency"], "side": proposal["side"],
        "purpose": proposal["purpose"], "quantity": proposal["quantity"],
        "order_type": proposal["order_type"], "time_in_force": proposal["time_in_force"],
        "limit_price_usd": proposal["limit_price_usd"],
    }


def _new_submission(payload, record, state, at):
    command = _command(record, payload)
    return {
        "schema": RECORD_SCHEMA, "operation_id": payload["operation_id"],
        "intent_id": record["intent_id"], "client_order_id": record["client_order_id"],
        "request": payload, "request_sha256": store.digest(payload), "command": command,
        "command_sha256": store.digest(command), "state": state,
        "broker_order_id": None, "reason": None, "marked_at": at.isoformat(),
        "resolved_at": None, "owner_id": payload["owner_id"], "epoch": payload["epoch"],
        "last_event_version": 0,
    }


def mark_submission(path, payload):
    payload = _request(payload, SUBMISSION_FIELDS, SUBMISSION_SCHEMA)
    operation_id = store._identity(payload["operation_id"], "operation id")
    intent_id = store._identity(payload["intent_id"], "intent id")
    owner_id = store._identity(payload["owner_id"], "owner id")
    epoch = store._version(payload["epoch"], "writer epoch")
    expected_account = store._version(payload["expected_account_version"], "expected account version")
    at = store._timestamp_string(payload["at"], "submission time")
    with store.database(path, write=True) as connection:
        account = store._read_state(connection)
        writer, submissions, events = _read_writer(connection)
        reconciliation = None
        if connection.execute("PRAGMA user_version").fetchone()[0] >= 3:
            from . import order_reconciliation
            reconciliation, _ = order_reconciliation._read(connection)
        existing = submissions.get(operation_id)
        by_intent = next((row for row in submissions.values() if row["intent_id"] == intent_id), None)
        if existing is not None and existing["request"] == payload:
            return {"schema": SUBMISSION_SCHEMA, "outcome": existing["state"],
                    "duplicate": True, "should_call_adapter": False,
                    "submission": existing, "writer": _report(connection, writer, submissions),
                    "live_trading_enabled": False}
        if reconciliation is not None and reconciliation["status"] != "reconciled":
            raise ValueError("Reconciliation is required before marking a submission")
        if existing is not None or by_intent is not None:
            previous_incident = next((event for event in events
                                      if event["kind"] == "writer_incident"
                                      and event["request"] == payload), None)
            if previous_incident is not None:
                return {"schema": SUBMISSION_SCHEMA, "outcome": "identity_conflict",
                        "duplicate": True, "should_call_adapter": False,
                        "writer": _report(connection, writer, submissions),
                        "live_trading_enabled": False}
            if writer["disarmed"] or writer["unresolved_reasons"]:
                raise ValueError("Writer is disarmed")
            if (writer["owner_id"], writer["epoch"]) != (owner_id, epoch):
                raise ValueError("Writer ownership or fencing epoch changed")
            _require_monotonic(at, events)
            writer["disarmed"] = True
            writer["unresolved_reasons"] = sorted(set(
                writer["unresolved_reasons"] + ["writer_identity_conflict"]))
            writer, _, _ = _append_event(connection, "writer_incident", at, payload, writer)
            result = _report(connection, writer, submissions)
            return {"schema": SUBMISSION_SCHEMA, "outcome": "identity_conflict",
                    "duplicate": False, "should_call_adapter": False,
                    "writer": result, "live_trading_enabled": False}
        if writer["disarmed"] or writer["unresolved_reasons"]:
            raise ValueError("Writer is disarmed")
        if (writer["owner_id"], writer["epoch"]) != (owner_id, epoch):
            raise ValueError("Writer ownership or fencing epoch changed")
        if account["version"] != expected_account:
            raise ValueError("Account version changed; read status before submission")
        _require_monotonic(at, events)
        row = connection.execute("SELECT payload FROM intents WHERE intent_id=?", (intent_id,)).fetchone()
        if row is None:
            raise ValueError("Submission intent is not admitted")
        record = store._record_payload(row[0])
        if record["state"] != "reserved":
            raise ValueError("Submission intent has no reservation")
        if connection.execute("SELECT 1 FROM reservation_releases WHERE intent_id=?", (intent_id,)).fetchone():
            raise ValueError("Submission authority was already cancelled")
        proposal = record["proposal"]
        if at < utc(proposal["decision_at"]):
            raise ValueError("Submission predates its admission decision")
        for name in ("ledger", "risk", "evidence"):
            if proposal[f"expected_{name}_version"] != account[f"{name}_version"]:
                raise ValueError(f"{name.capitalize()} evidence changed; submission requires reconciliation")
        if proposal["expected_policy_sha256"] != store.digest(account["policy"]):
            raise ValueError("Risk policy changed; submission requires reconciliation")
        if account["halt_reasons"] or account["unresolved_reasons"]:
            raise ValueError("Account is halted or unresolved")
        if at >= utc(record["reservation"]["expires_at"]):
            store._release_reservation(connection, account, record, payload["at"])
            submission = _new_submission(payload, record, "cancelled", at)
            submission.update(reason="expired_authority", resolved_at=at.isoformat())
            writer, submission, _ = _append_event(
                connection, "submission_expired", at, payload, writer, submission)
            submissions[operation_id] = submission
            return {"schema": SUBMISSION_SCHEMA, "outcome": "cancelled",
                    "duplicate": False, "should_call_adapter": False,
                    "submission": submission, "writer": _report(connection, writer, submissions),
                    "live_trading_enabled": False}
        for label in ("quote_at", "fx_at"):
            observed = utc(proposal[label])
            age = at - observed
            if not store.timedelta(0) <= age <= store.MAX_FRESHNESS:
                raise ValueError(f"Bound {label.replace('_at', '')} is stale or future-dated")
        submission = _new_submission(payload, record, "submitting", at)
        writer, submission, _ = _append_event(
            connection, "submission_marked", at, payload, writer, submission)
        submissions[operation_id] = submission
        return {"schema": SUBMISSION_SCHEMA, "outcome": "submitting",
                "duplicate": False, "should_call_adapter": True,
                "submission": submission, "writer": _report(connection, writer, submissions),
                "live_trading_enabled": False}


def _record_result(path, operation_id, owner_id, epoch, at, result):
    if not isinstance(result, dict) or result.get("outcome") not in {
            "acknowledged", "rejected", "unknown"}:
        raise ValueError("Invalid synthetic adapter result")
    expected_fields = ({"outcome", "broker_order_id"}
                       if result["outcome"] == "acknowledged" else {"outcome", "reason"})
    if set(result) != expected_fields:
        raise ValueError("Synthetic adapter result fields do not match its outcome")
    if result["outcome"] == "acknowledged":
        store._identity(result["broker_order_id"], "broker order id")
    else:
        store._identity(result["reason"], "adapter result reason")
    with store.database(path, write=True) as connection:
        store._read_state(connection)
        writer, submissions, events = _read_writer(connection)
        result_at = store._timestamp_string(at, "adapter result time")
        _require_monotonic(result_at, events)
        record = submissions.get(operation_id)
        if record is None or record["state"] != "submitting":
            raise ValueError("Submission is not awaiting an adapter result")
        if (writer["owner_id"], writer["epoch"]) != (owner_id, epoch):
            raise ValueError("Writer lost ownership before result commit")
        record = deepcopy(record)
        record["state"] = result["outcome"]
        record["resolved_at"] = result_at.isoformat()
        record["broker_order_id"] = result.get("broker_order_id")
        record["reason"] = result.get("reason")
        if record["state"] in ("unknown", "rejected"):
            writer["disarmed"] = True
            reason = "submission_unknown" if record["state"] == "unknown" else "submission_rejected"
            writer["unresolved_reasons"] = sorted(set(writer["unresolved_reasons"] + [reason]))
        event_request = {"operation_id": operation_id, "adapter_result": result}
        writer, record, _ = _append_event(
            connection, "submission_result", at, event_request, writer, record)
        submissions[operation_id] = record
        return {"schema": SUBMISSION_SCHEMA, "outcome": record["state"],
                "duplicate": False, "should_call_adapter": False,
                "submission": record, "writer": _report(connection, writer, submissions),
                "live_trading_enabled": False}


def dispatch_synthetic(path, payload, outcome, adapter=None):
    if outcome not in SYNTHETIC_OUTCOMES:
        raise ValueError("Unsupported synthetic adapter outcome")
    adapter = adapter or SyntheticAdapter()
    marked = mark_submission(path, payload)
    if not marked["should_call_adapter"]:
        return marked
    command = marked["submission"]["command"]
    try:
        result = adapter.submit(command, outcome)
    except SubmissionUncertain:
        result = {"outcome": "unknown", "reason": "lost_acknowledgement"}
    return _record_result(
        path, payload["operation_id"], payload["owner_id"], payload["epoch"],
        payload["at"], result,
    )


def recover(path, payload):
    payload = _request(payload, RECOVERY_FIELDS, RECOVERY_SCHEMA)
    recovery_id = store._identity(payload["recovery_id"], "recovery id")
    owner_id = store._identity(payload["owner_id"], "owner id")
    epoch = store._version(payload["epoch"], "writer epoch")
    at = store._timestamp_string(payload["at"], "recovery time")
    with store.database(path, write=True) as connection:
        store._read_state(connection)
        writer, submissions, events = _read_writer(connection)
        previous = next((event for event in events
                         if event["kind"] == "writer_recovered"
                         and event["request"].get("recovery_id") == recovery_id), None)
        if previous is not None:
            if previous["request"] != payload:
                raise ValueError("Writer recovery identity was reused with changed input")
            result = _report(connection, writer, submissions)
            result.update(outcome="recovered", duplicate=True)
            return result
        _require_monotonic(at, events)
        if (writer["owner_id"], writer["epoch"]) != (owner_id, epoch):
            raise ValueError("Only the current fenced owner may recover the writer")
        inflight = [row for row in submissions.values() if row["state"] == "submitting"]
        if len(inflight) > 1:
            raise ValueError("Multiple in-flight submissions violate the account slot")
        submission = None
        if inflight:
            submission = deepcopy(inflight[0])
            submission.update(state="unknown", reason="restart_during_submission",
                              resolved_at=at.isoformat())
            writer["unresolved_reasons"] = sorted(set(
                writer["unresolved_reasons"] + ["submission_unknown"]))
        writer.update(owner_id=None, claim_id=None, claimed_at=None, disarmed=True)
        writer, submission, _ = _append_event(
            connection, "writer_recovered", at, payload, writer, submission)
        if submission is not None:
            submissions[submission["operation_id"]] = submission
        if connection.execute("PRAGMA user_version").fetchone()[0] >= 3:
            from . import order_reconciliation
            order_reconciliation._invalidate_connection(connection, {
                "schema": "order-reconciliation-invalidation-v1",
                "event_id": recovery_id, "at": at.isoformat(), "reason": "startup",
            }, writer_already_disarmed=True)
            writer, submissions, _ = _read_writer(connection)
        result = _report(connection, writer, submissions)
        result.update(outcome="recovered", duplicate=False)
        return result
