"""P4.5 G: actual SQLite, fenced synthetic adapters and cumulative evidence."""
from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy
from datetime import datetime, timedelta, timezone
from decimal import Decimal as D
import contextlib
import json
from pathlib import Path
import sqlite3
import subprocess
import sys
import tempfile
import unittest

from trad3r import order_allocations as allocations
from trad3r import order_cancellation as cancellations
from trad3r import order_controls as controls
from trad3r import order_reconciliation as entries
from trad3r import order_reducing_dispatch as dispatch
from trad3r import order_sell_reconciliation as sells
from trad3r import order_store as store
from trad3r import order_writer as writer
from trad3r.settlement import (CASH_RELEASE_POLICY, SETTLEMENT_CALENDAR_ID,
                               cash_available_at, settlement_date)


class Rehearsal:
    """Invented broker evidence; requests always bind the actual persisted versions."""
    instrument = "synthetic:NASDAQ:AAPL:USD"

    def __init__(self, path, quantity=1):
        self.path = path
        self.time = datetime(2026, 9, 4, 14, tzinfo=timezone.utc)
        self.mark = {"equity": "1000", "deposits": "0", "withdrawals": "0"}
        allocations.initialize(path, {
            "schema": "synthetic-order-account-v1", "account_id": "synthetic-test",
            "environment": "synthetic", "at": self.at(), "settled_cash_usd": "500",
            "position_quantity": 0, "mark": self.mark, "session_start": self.mark,
            "week_start": self.mark, "ledger_version": 4, "risk_version": 7,
            "evidence_version": 2, "halt_reasons": [],
        })
        decision_at = self.at()
        self.entry_request = {
            "schema": "order-admission-v1", "account_id": "synthetic-test",
            "environment": "synthetic", "intent_id": "entry-intent",
            "candidate_id": "entry-candidate", "client_order_id": "entry-order",
            "decision_at": decision_at, "expires_at": self.expiry(),
            "expected_account_version": 0, "expected_ledger_version": 4,
            "expected_risk_version": 7, "expected_evidence_version": 2,
            "expected_policy_sha256": store.digest(store._policy_payload()),
            "instrument_id": self.instrument, "symbol": "AAPL", "currency": "USD",
            "side": "buy", "purpose": "entry", "quantity": 2, "order_type": "limit",
            "time_in_force": "day", "limit_price_usd": "100", "stop_price_usd": "99.5",
            "entry_fee_usd": "0.35", "exit_fee_usd": "0.35",
            "slippage_usd_per_share": "0.05", "usd_to_gbp": "0.8",
            "quote_at": decision_at, "fx_at": decision_at,
        }
        store.admit(path, self.entry_request)
        self.admitted = store.status(path)
        self.claim()
        self.entry_adapter = writer.SyntheticAdapter()
        result = writer.dispatch_synthetic(path, {
            "schema": "order-submission-operation-v1", "operation_id": "entry-submit",
            "intent_id": "entry-intent", "owner_id": "manager", "epoch": 1,
            "at": self.at(), "expected_account_version": 1,
        }, "acknowledged", self.entry_adapter)
        broker = result["submission"]["broker_order_id"]
        self.orders = [{"client_order_id": "entry-order", "order_id": broker,
                        "side": "buy", "state": "filled" if quantity == 2 else "working",
                        "original_quantity": 2, "cumulative_executed_quantity": quantity}]
        self.executions = [{"execution_id": "entry-fill", "client_order_id": "entry-order",
            "order_id": broker, "instrument_id": self.instrument, "symbol": "AAPL",
            "currency": "USD", "side": "buy", "quantity": quantity,
            "price_usd": "100", "at": self.at()}]
        self.fees = [{"commission_id": "entry-fee", "execution_id": "entry-fill",
            "currency": "USD", "amount_usd": "0.35", "at": self.at(), "revision": 0,
            "final": True}]
        self.quantity = quantity
        self.cash = str(D("500") - D("100") * quantity - D("0.35"))
        self.pending = []
        self.exit_adapter = dispatch.SyntheticReducingAdapter()
        self.cancel_adapter = cancellations.SyntheticCancellationAdapter()
        self.entry_proof()

    def at(self):
        self.time += timedelta(seconds=1)
        return self.time.isoformat()

    def expiry(self):
        return (self.time + timedelta(seconds=50)).isoformat()

    def versions(self):
        with store.database(self.path) as connection:
            return (store._read_state(connection), entries._read(connection)[0],
                    sells._read(connection)[0], writer._read_writer(connection)[0],
                    allocations._read(connection)[0], cancellations._read(connection)[0],
                    dispatch._read(connection)[0])

    def claim(self):
        state = writer.status(self.path)
        return writer.claim(self.path, {"schema": "order-writer-claim-v1",
            "claim_id": "claim-" + str(state["epoch"]), "owner_id": "manager",
            "at": self.at(), "expected_epoch": state["epoch"]})

    def common_snapshot(self):
        at = self.at()
        return {"account_id": "synthetic-test", "environment": "synthetic", "at": at,
            "snapshot_id": "snapshot-" + str(int(self.time.timestamp())), "reconciliation_id": "reconcile-" + str(int(self.time.timestamp())),
            "completeness": {key: True for key in (
                "orders", "executions", "positions", "currency_cash", "commissions", "settlement")},
            "orders": deepcopy(self.orders), "executions": deepcopy(self.executions),
            "commissions": deepcopy(self.fees), "currency_cash": {"USD": self.cash},
            "positions": ([{"instrument_id": self.instrument, "symbol": "AAPL",
                           "currency": "USD", "quantity": self.quantity}] if self.quantity else []),
            "unsettled_usd": str(sum((D(lot["net_usd"]) for lot in self.pending), D("0"))),
            "pending_settlements": deepcopy(self.pending), "mark": deepcopy(self.mark)}

    def entry_proof(self):
        snapshot = self.common_snapshot()
        snapshot.update(schema="synthetic-reconciliation-snapshot-v1",
                        expected_reconciliation_version=entries.status(self.path)["version"])
        for row in snapshot["orders"]:
            row["broker_order_id"] = row.pop("order_id")
            del row["side"]
        for row in snapshot["executions"]:
            row["broker_order_id"] = row.pop("order_id")
        for row in snapshot["commissions"]:
            del row["final"]
        return entries.apply(self.path, snapshot)

    def snapshot(self):
        account, _, reducing, managed, allocated, _, _ = self.versions()
        snapshot = self.common_snapshot()
        snapshot.update(schema="synthetic-reducing-reconciliation-v1",
            expected_reducing_reconciliation_version=reducing["version"],
            expected_account_version=account["version"],
            expected_writer_version=managed["version"],
            expected_allocation_version=allocated["version"])
        return snapshot

    def proof(self):
        return sells.apply(self.path, self.snapshot())

    def allocation_request(self, identity, quantity, fee="0.35", purpose="reducing_exit"):
        account, entry, _, managed, allocated, _, _ = self.versions()
        at = self.at()
        return {"schema": "reducing-allocation-request-v1", "allocation_id": identity,
            "client_order_id": identity + "-order", "account_id": "synthetic-test",
            "environment": "synthetic", "entry_intent_id": "entry-intent",
            "instrument_id": self.instrument, "purpose": purpose, "quantity": quantity,
            "fee_bound_usd": fee, "decision_at": at, "expires_at": self.expiry(),
            "quote_at": at, "fx_at": at, "owner_id": "manager",
            "writer_epoch": managed["epoch"], "expected_account_version": account["version"],
            "expected_reconciliation_version": entry["version"],
            "expected_writer_version": managed["version"],
            "expected_allocation_version": allocated["version"],
            "expected_policy_sha256": self.entry_request["expected_policy_sha256"]}

    def allocate(self, identity, quantity, fee="0.35", purpose="reducing_exit"):
        return allocations.admit(self.path, self.allocation_request(identity, quantity, fee, purpose))

    def command_versions(self):
        account, entry, reducing, managed, allocated, cancelled, dispatched = self.versions()
        return {"account_id": "synthetic-test", "environment": "synthetic",
            "owner_id": "manager", "writer_epoch": managed["epoch"],
            "expected_account_version": account["version"],
            "expected_entry_reconciliation_version": entry["version"],
            "expected_reducing_reconciliation_version": reducing["version"],
            "expected_writer_version": managed["version"],
            "expected_allocation_version": allocated["version"],
            "expected_cancellation_version": cancelled["version"],
            "expected_dispatch_version": dispatched["version"]}

    def dispatch_request(self, identity, stop=False):
        request = self.command_versions()
        request.update(schema="reducing-dispatch-request-v1", operation_id="submit-" + identity,
            allocation_id=identity, at=self.at(), expires_at=self.expiry(),
            order_type="stop" if stop else "limit", time_in_force="day",
            limit_price_usd=None if stop else "99.5", stop_price_usd="99.5" if stop else None)
        return request

    def submit(self, identity, quantity, stop=False, outcome="acknowledged"):
        request = self.dispatch_request(identity, stop)
        result = dispatch.dispatch_synthetic(self.path, request, outcome, self.exit_adapter)
        if outcome == "acknowledged":
            self.orders.append({"client_order_id": identity + "-order",
                "order_id": result["operation"]["broker_order_id"], "side": "sell",
                "state": "working", "original_quantity": quantity, "cumulative_executed_quantity": 0})
        return request, result

    def cancel_request(self, order):
        request = self.command_versions()
        del request["expected_dispatch_version"]
        request.update(schema="order-cancellation-request-v1", operation_id="cancel-" + order["client_order_id"],
            target_client_order_id=order["client_order_id"], target_order_id=order["order_id"],
            at=self.at(), expires_at=self.expiry())
        return request

    def cancel(self, order):
        request = self.cancel_request(order)
        cancellations.dispatch_synthetic(self.path, request, "accepted", self.cancel_adapter)
        return request

    def fill(self, order, quantity, price="99.5", fee="0.35", final=True):
        execution_id = "fill-" + str(len(self.executions))
        self.executions.append({"execution_id": execution_id,
            "client_order_id": order["client_order_id"], "order_id": order["order_id"],
            "instrument_id": self.instrument, "symbol": "AAPL", "currency": "USD",
            "side": "sell", "quantity": quantity, "price_usd": price, "at": self.at()})
        order["cumulative_executed_quantity"] += quantity
        if order["cumulative_executed_quantity"] == order["original_quantity"]:
            order["state"] = "filled"
        self.quantity -= quantity
        if fee is not None:
            self.fees.append({"commission_id": "fee-" + execution_id, "execution_id": execution_id,
                "currency": "USD", "amount_usd": fee, "at": self.at(), "revision": 0, "final": final})
        fee_bound = fee if fee is not None else "0.35"
        due = settlement_date("2026-09-04")
        gross = D(price) * quantity
        self.pending.append({"execution_id": execution_id, "gross_usd": str(gross),
            "fee_usd": fee_bound, "fee_status": "missing" if fee is None else "final" if final else "provisional",
            "net_usd": str(gross - D(fee_bound)), "settles_on": due.isoformat(),
            "available_at": cash_available_at(due).isoformat(),
            "settlement_calendar_id": SETTLEMENT_CALENDAR_ID, "cash_release_policy": CASH_RELEASE_POLICY})

    def pause(self):
        state = controls.status(self.path)
        return controls.apply(self.path, {"schema": controls.SCHEMA, "control_id": "pause",
            "account_id": "synthetic-test", "environment": "synthetic", "at": self.at(),
            "action": "pause", "incident_id": None, "expected_version": state["version"],
            "expected_sources": state["sources"]})

    def cancel_entry(self):
        self.claim()
        request = self.cancel(self.orders[0])
        self.orders[0]["state"] = "cancelled"
        self.entry_proof()
        return request

    def working_stop(self):
        self.claim()
        self.allocate("stop", self.quantity, purpose="protective_stop")
        request, result = self.submit("stop", self.quantity, stop=True)
        self.proof()
        return request, result


# A separate interpreter deliberately exits without Python cleanup. The durable
# adapter receipt is outside SQLite, so rolled-back results cannot hide a call.
CRASH_WORKER = r'''
import json, os, sqlite3, sys
from pathlib import Path
from trad3r import order_cancellation, order_reducing_dispatch
path, request_path, receipt_path, kind, boundary = sys.argv[1:]
module = order_cancellation if kind == "cancel" else order_reducing_dispatch
request = json.loads(Path(request_path).read_text())
if boundary == "before_marker":
    os._exit(73)
if boundary == "after_marker":
    module.mark(path, request)
    os._exit(73)
class Adapter:
    def perform(self, command, outcome):
        with open(receipt_path, "a", encoding="utf-8") as receipt:
            receipt.write(json.dumps(command, sort_keys=True) + "\n")
            receipt.flush()
            os.fsync(receipt.fileno())
        if boundary == "after_acceptance":
            os._exit(73)
        return ({"outcome": "accepted", "receipt_id": "external-receipt"} if kind == "cancel"
                else {"outcome": "acknowledged", "broker_order_id": "external-order"})
    cancel = perform
    submit = perform
try:
    module.dispatch_synthetic(path, request, "accepted" if kind == "cancel" else "acknowledged", Adapter())
except sqlite3.IntegrityError:
    if boundary != "result_commit":
        raise
    os._exit(73)
raise AssertionError("Fault was not reached")
'''


class ProtectionRehearsalTests(unittest.TestCase):
    def setUp(self):
        self.root = tempfile.TemporaryDirectory()
        self.addCleanup(self.root.cleanup)
        self.path = Path(self.root.name) / "orders.sqlite"

    def test_numeric_entry_cancel_stop_cancel_exit_preserves_pause_halt_and_attempts(self):
        r = Rehearsal(self.path)
        self.assertEqual([D(r.admitted[key]) for key in (
            "reserved_cash_usd", "reserved_exposure_gbp", "reserved_loss_gbp")], [D("200.80"), D("160.08"), D("1.52")])
        self.assertEqual(store.status(self.path)["reserved_cash_usd"], "100.40")
        r.mark["equity"] = "989"
        r.entry_proof()
        r.pause()
        cancel_entry = r.cancel_entry()
        account = store.status(self.path)
        self.assertEqual([account[key] for key in (
            "position_quantity", "settled_cash_usd", "reserved_cash_usd",
            "reserved_exposure_gbp", "reserved_loss_gbp")], [1, "399.65", "0.35", "160.080", "1.520"])
        stop_request, _ = r.working_stop()
        self.assertEqual(controls.status(self.path)["facts"]["covered_quantity"], 1)
        r.claim()
        self.assertEqual(r.allocate("competing", 1)["outcome"], "rejected")
        cancel_stop = r.cancel(r.orders[1])
        self.assertEqual(controls.status(self.path)["facts"]["covered_quantity"], 0)
        r.orders[1]["state"] = "cancelled"
        self.assertEqual(r.proof()["available_sell_quantity"], 1)
        r.claim()
        self.assertEqual(r.allocate("exit", 1)["outcome"], "reserved")
        exit_request, _ = r.submit("exit", 1)
        r.fill(r.orders[2], 1)
        snapshot = r.snapshot()
        sells.apply(self.path, snapshot)
        before = store.status(self.path)
        self.assertEqual((before["settled_cash_usd"], before["unsettled_usd"], before["position_quantity"]),
                         ("399.65", "99.15", 0))
        self.assertEqual(D(before["settled_cash_usd"]) + D(before["unsettled_usd"]), D("498.80"))
        for key in ("reserved_cash_usd", "reserved_exposure_gbp", "reserved_loss_gbp"):
            self.assertEqual(D(before[key]), 0)
        self.assertEqual(before["attempts"], 1)
        self.assertIn("daily", before["blocked_reasons"])
        facts = controls.status(self.path)
        self.assertTrue(facts["operator_paused"])
        self.assertEqual((facts["facts"]["exposure"], facts["facts"]["protection"]), ("verified_flat", "not_required"))
        self.assertTrue(sells.apply(self.path, snapshot)["duplicate"])
        r.mark["equity"] = "1000"
        r.proof()  # Same executions under a new envelope cannot change cash or clear the halt.
        for request in (stop_request, exit_request):
            self.assertTrue(dispatch.dispatch_synthetic(self.path, request, "acknowledged", r.exit_adapter)["duplicate"])
        for request in (cancel_entry, cancel_stop):
            self.assertTrue(cancellations.dispatch_synthetic(self.path, request, "accepted", r.cancel_adapter)["duplicate"])
        after = store.status(self.path)
        for key in ("settled_cash_usd", "unsettled_usd", "position_quantity", "attempts"):
            self.assertEqual(before[key], after[key])
        self.assertIn("daily", after["blocked_reasons"])
        self.assertEqual((r.entry_adapter.calls, r.exit_adapter.calls, r.cancel_adapter.calls), (1, 2, 2))
        with store.database(self.path) as connection:
            self.assertEqual(connection.execute("SELECT count(*) FROM reducing_dispatch_events WHERE kind='marked'").fetchone()[0], 2)
            self.assertEqual(connection.execute("SELECT count(*) FROM cancellation_events WHERE kind='marked'").fetchone()[0], 2)

    def test_stop_fill_during_cancel_dispatches_only_verified_residual(self):
        for filled in (1, 2):
            with self.subTest(filled=filled):
                path = self.path.with_name(f"residual-{filled}.sqlite")
                r = Rehearsal(path, quantity=2)
                r.working_stop()
                r.claim()
                request = r.cancel_request(r.orders[1])
                cancellations.mark(path, request)
                r.fill(r.orders[1], filled, fee="0.15" if filled == 1 else "0.35")
                evidence = r.proof()
                self.assertEqual((evidence["verified_quantity"], evidence["committed_sell_quantity"],
                                  evidence["available_sell_quantity"]), (2 - filled, 2 - filled, 0))
                result = cancellations._record_result(path, request["operation_id"], "manager",
                    request["writer_epoch"], r.at(), {"outcome": "accepted", "receipt_id": "late"})
                self.assertEqual(result["outcome"], "accepted" if filled == 1 else "moot_filled")
                if filled == 1:
                    r.orders[1]["state"] = "cancelled"
                    self.assertEqual(r.proof()["available_sell_quantity"], 1)
                    r.claim()
                    self.assertEqual(r.allocate("residual", 1, "0.20")["outcome"], "reserved")
                    _, submitted = r.submit("residual", 1)
                    self.assertEqual(submitted["operation"]["command"]["quantity"], 1)
                    r.fill(r.orders[2], 1, fee="0.20")
                    r.proof()
                self.assertEqual(r.exit_adapter.calls, 2 if filled == 1 else 1)
                self.assertEqual(store.status(path)["position_quantity"], 0)
                self.assertEqual(store.status(path)["attempts"], 1)

    def test_late_cancelled_stop_fill_retains_replacement_and_capacity_incident(self):
        r = Rehearsal(self.path, quantity=2)
        r.working_stop()
        r.claim()
        r.cancel(r.orders[1])
        r.orders[1]["state"] = "cancelled"
        r.proof()
        r.claim()
        r.allocate("replacement", 2)
        before = store.status(self.path)
        r.fill(r.orders[1], 2)
        incoming = r.snapshot()
        result = sells.apply(self.path, incoming)
        self.assertEqual(result["outcome"], "unresolved")
        self.assertIn("sell_commitment_exceeds_holdings", result["unresolved_reasons"])
        self.assertTrue(writer.status(self.path)["disarmed"])
        for key in ("settled_cash_usd", "unsettled_usd", "position_quantity", "attempts"):
            self.assertEqual(store.status(self.path)[key], before[key])
        incident_state = controls.status(self.path)["incidents"]
        self.assertTrue(any(row["status"] == "open" for row in incident_state))
        self.assertTrue(sells.apply(self.path, incoming)["duplicate"])
        r.proof()
        self.assertEqual(controls.status(self.path)["incidents"], incident_state)
        with self.assertRaises(ValueError):
            r.claim()
        blocked_adapter = dispatch.SyntheticReducingAdapter()
        with self.assertRaises(ValueError):
            dispatch.dispatch_synthetic(self.path, r.dispatch_request("replacement"), "acknowledged", blocked_adapter)
        self.assertEqual(blocked_adapter.calls, 0)
        with store.database(self.path) as connection:
            retained = "\n".join(row[0] for row in connection.execute("SELECT payload FROM reducing_reconciliation_inbox"))
        self.assertIn(r.executions[-1]["execution_id"], retained)
        self.assertEqual({row["allocation_id"] for row in allocations.status(self.path)["allocations"]}, {"stop", "replacement"})

    def test_concurrent_distinct_full_exits_reserve_and_dispatch_exactly_one(self):
        r = Rehearsal(self.path, quantity=2)
        r.claim()
        requests = [r.allocation_request(name, 2) for name in ("first", "second")]
        for key in ("decision_at", "expires_at", "quote_at", "fx_at"):
            requests[1][key] = requests[0][key]
        def reserve(request):
            try:
                return allocations.admit(self.path, request)
            except ValueError as error:
                return str(error)
        with ThreadPoolExecutor(max_workers=2) as pool:
            results = list(pool.map(reserve, requests))
        self.assertEqual(sum(isinstance(row, dict) and row["outcome"] == "reserved" for row in results), 1)
        self.assertTrue(any(isinstance(row, str) and "version" in row.lower() for row in results))
        allocated = allocations.status(self.path)["allocations"]
        winner = allocated[0]["allocation_id"]
        loser = "second" if winner == "first" else "first"
        self.assertEqual(r.allocate(loser, 2)["outcome"], "rejected")
        for identity in (winner, loser):
            request = r.dispatch_request(identity)
            if identity == loser:
                with self.assertRaises(ValueError):
                    dispatch.dispatch_synthetic(self.path, request, "acknowledged", r.exit_adapter)
            else:
                dispatch.dispatch_synthetic(self.path, request, "acknowledged", r.exit_adapter)
        self.assertEqual(r.exit_adapter.calls, 1)
        self.assertEqual(store.status(self.path)["attempts"], 1)

    def test_process_death_and_result_rollback_never_repeat_adapter_calls(self):
        for kind in ("cancel", "reduce"):
            for boundary in ("before_marker", "after_marker", "after_acceptance", "result_commit"):
                with self.subTest(kind=kind, boundary=boundary):
                    name = kind + "-" + boundary
                    path = self.path.with_name(name + ".sqlite")
                    r = Rehearsal(path)
                    r.claim()
                    if kind == "cancel":
                        module, adapter = cancellations, r.cancel_adapter
                        request, outcome = r.cancel_request(r.orders[0]), "accepted"
                        table = "cancellation_events"
                    else:
                        module, adapter = dispatch, r.exit_adapter
                        r.allocate("exit", 1)
                        request, outcome = r.dispatch_request("exit"), "acknowledged"
                        table = "reducing_dispatch_events"
                    request_path = path.with_suffix(".json")
                    receipt = path.with_suffix(".receipt")
                    request_path.write_text(json.dumps(request), encoding="utf-8")
                    if boundary == "result_commit":
                        with contextlib.closing(sqlite3.connect(path)) as connection, connection:
                            connection.execute(f"CREATE TRIGGER fail_result BEFORE INSERT ON {table} "
                                               "WHEN NEW.kind='result' BEGIN SELECT RAISE(ABORT,'injected result failure'); END")
                    child = subprocess.run([sys.executable, "-c", CRASH_WORKER, str(path),
                        str(request_path), str(receipt), kind, boundary], capture_output=True, text=True, timeout=60)
                    self.assertEqual(child.returncode, 73, child.stderr)
                    before = store.status(path)
                    if boundary == "result_commit":
                        with contextlib.closing(sqlite3.connect(path)) as connection, connection:
                            connection.execute("DROP TRIGGER fail_result")
                    result = module.dispatch_synthetic(path, request, outcome, adapter)
                    self.assertEqual(result["duplicate"], boundary != "before_marker")
                    self.assertEqual(adapter.calls, int(boundary == "before_marker"))
                    external_calls = len(receipt.read_text().splitlines()) if receipt.exists() else 0
                    self.assertEqual(external_calls, int(boundary in ("after_acceptance", "result_commit")))
                    self.assertLessEqual(adapter.calls + external_calls, 1)
                    self.assertEqual(store.status(path)["position_quantity"], before["position_quantity"])
                    self.assertEqual(store.status(path)["settled_cash_usd"], before["settled_cash_usd"])
                    if boundary != "before_marker":
                        self.assertIsNone(result["operation"]["adapter_result"])
                        self.assertTrue(module.status(path)["unresolved_reasons"])
                    with store.database(path) as connection:
                        self.assertEqual(connection.execute(f"SELECT count(*) FROM {table} WHERE kind='marked'").fetchone()[0], 1)
                        self.assertEqual(connection.execute(f"SELECT count(*) FROM {table} WHERE kind='result'").fetchone()[0], int(boundary == "before_marker"))

    def test_one_share_fee_revision_and_cutoff_restart_keep_pending_unspendable(self):
        r = Rehearsal(self.path)
        r.cancel_entry()
        r.claim()
        r.allocate("exit", 1)
        r.submit("exit", 1)
        r.fill(r.orders[1], 1)
        r.proof()
        r.fees[-1].update(amount_usd="0.45", revision=1, at=r.at())
        r.pending[-1].update(fee_usd="0.45", net_usd="99.05")
        r.mark["equity"] = "989"
        revision = r.snapshot()
        sells.apply(self.path, revision)
        self.assertTrue(sells.apply(self.path, revision)["duplicate"])
        r.mark["equity"] = "1000"
        r.proof()
        account = store.status(self.path)
        self.assertEqual((account["settled_cash_usd"], account["unsettled_usd"]), ("399.65", "99.05"))
        self.assertIn("daily", account["blocked_reasons"])
        lot = sells.status(self.path)["pending_lots"][0]
        self.assertEqual(lot["settles_on"], "2026-09-08")
        self.assertEqual(lot["available_at"], "2026-09-09T04:00:00+00:00")
        child = subprocess.run([sys.executable, "-c",
            "import json,sys; from trad3r import order_store; print(json.dumps(order_store.status(sys.argv[1]), default=str))",
            str(self.path)], capture_output=True, text=True, timeout=60)
        self.assertEqual(child.returncode, 0, child.stderr)
        self.assertEqual(json.loads(child.stdout), json.loads(json.dumps(account, default=str)))
        r.time = datetime(2026, 9, 9, 4, tzinfo=timezone.utc)
        with self.assertRaisesRegex(ValueError, "period transition"):
            r.proof()
        self.assertEqual(store.status(self.path), account)
        self.assertFalse(sells.status(self.path)["settlement_release_enabled"])

    def test_stop_gap_and_day_expiry_do_not_infer_flatness(self):
        for gap in (False, True):
            with self.subTest(gap=gap):
                path = self.path.with_name(f"gap-{gap}.sqlite")
                r = Rehearsal(path, quantity=2)
                r.working_stop()
                self.assertEqual(store.status(path)["position_quantity"], 2)
                if gap:
                    r.fill(r.orders[1], 2, price="90")
                    r.mark["equity"] = "980"
                    r.proof()
                    self.assertEqual(store.status(path)["unsettled_usd"], "179.65")
                    self.assertIn("daily", store.status(path)["blocked_reasons"])
                else:
                    # DAY expiry is broker terminal-cancellation evidence, not a local timer.
                    r.time = datetime(2026, 9, 4, 20, tzinfo=timezone.utc)
                    r.orders[1]["state"] = "cancelled"
                    r.proof()
                    facts = controls.status(path)["facts"]
                    self.assertEqual((facts["exposure"], facts["protection"], facts["covered_quantity"]),
                                     ("verified_long", "missing", 0))
                    self.assertEqual(store.status(path)["position_quantity"], 2)
                    self.assertTrue(controls.status(path)["incidents"])

    def test_stop_uncertainty_blocks_replacement_but_rejection_allows_fresh_exit(self):
        for outcome in ("rejected", "accept_then_timeout", "submitting", "cancel_pending"):
            with self.subTest(outcome=outcome):
                path = self.path.with_name(outcome + ".sqlite")
                r = Rehearsal(path, quantity=2)
                r.claim()
                r.allocate("stop", 2, purpose="protective_stop")
                planned = controls.status(path)["facts"]
                self.assertEqual((planned["protection"], planned["covered_quantity"]), ("pending", 0))
                request = r.dispatch_request("stop", stop=True)
                if outcome == "submitting":
                    dispatch.mark(path, request)
                elif outcome == "cancel_pending":
                    r.submit("stop", 2, stop=True)
                    r.proof()
                    r.claim()
                    r.cancel(r.orders[1])
                else:
                    dispatch.dispatch_synthetic(path, request, outcome, r.exit_adapter)
                facts = controls.status(path)["facts"]
                self.assertEqual(facts["covered_quantity"], 0)
                self.assertEqual(facts["committed_sell_quantity"], 0 if outcome == "rejected" else 2)
                if outcome == "accept_then_timeout":
                    # Complete position/cash evidence with no stop order cannot prove its absence.
                    report = r.proof()
                    self.assertEqual((report["committed_sell_quantity"], report["available_sell_quantity"]), (2, 0))
                    self.assertEqual(dispatch.status(path)["operations"][0]["state"], "unknown")
                if outcome == "rejected":
                    self.assertEqual(controls.status(path)["desired_action"], "flatten")
                    r.claim()
                    self.assertEqual(r.allocate("fresh-exit", 2)["outcome"], "reserved")
                    r.submit("fresh-exit", 2)
                    self.assertEqual(r.exit_adapter.calls, 2)
                else:
                    with self.assertRaises(ValueError):
                        r.allocate("unsafe-exit", 2)
                    blocked_adapter = dispatch.SyntheticReducingAdapter()
                    with self.assertRaises(ValueError):
                        dispatch.dispatch_synthetic(path, r.dispatch_request("unsafe-exit"), "acknowledged", blocked_adapter)
                    self.assertEqual(blocked_adapter.calls, 0)
                self.assertTrue(store.status(path)["blocked"])
                self.assertEqual(store.status(path)["attempts"], 1)

    def test_partial_entry_then_fill_before_cancel_response_preserves_two_shares(self):
        r = Rehearsal(self.path)
        r.claim()
        request = r.cancel_request(r.orders[0])
        cancellations.mark(self.path, request)
        second = deepcopy(r.executions[0])
        second.update(execution_id="entry-fill-two", at=r.at())
        r.executions.append(second)
        r.fees.append({"commission_id": "entry-fee-two", "execution_id": "entry-fill-two",
            "currency": "USD", "amount_usd": "0", "at": r.at(), "revision": 0, "final": True})
        r.orders[0].update(state="filled", cumulative_executed_quantity=2)
        r.quantity, r.cash = 2, "299.65"
        r.entry_proof()
        result = cancellations._record_result(self.path, request["operation_id"], "manager",
            request["writer_epoch"], r.at(), {"outcome": "accepted", "receipt_id": "late-entry-cancel"})
        self.assertEqual(result["outcome"], "moot_filled")
        self.assertEqual(result["operation"]["adapter_result"]["receipt_id"], "late-entry-cancel")
        account = store.status(self.path)
        self.assertEqual((account["position_quantity"], account["settled_cash_usd"], account["attempts"]),
                         (2, "299.65", 1))
        self.assertEqual(D(account["reserved_exposure_gbp"]), D("160.08"))
        self.assertTrue(cancellations.dispatch_synthetic(self.path, request, "accepted", r.cancel_adapter)["duplicate"])
        self.assertEqual(r.cancel_adapter.calls, 0)

    def test_missing_and_provisional_one_share_fee_retain_reservation_until_final(self):
        for fee, final in ((None, False), ("0.15", False)):
            with self.subTest(fee=fee):
                path = self.path.with_name("fee-" + str(fee) + ".sqlite")
                r = Rehearsal(path)
                r.cancel_entry()
                r.claim()
                r.allocate("exit", 1)
                r.submit("exit", 1)
                r.fill(r.orders[1], 1, fee=fee, final=final)
                report = r.proof()
                self.assertIn("fee_incomplete", report["unresolved_reasons"])
                account = store.status(path)
                self.assertTrue(account["blocked"])
                self.assertGreater(D(account["reserved_cash_usd"]), 0)
                self.assertEqual(account["settled_cash_usd"], "399.65")
                execution_id = r.executions[-1]["execution_id"]
                if fee is None:
                    r.fees.append({"commission_id": "fee-" + execution_id, "execution_id": execution_id,
                        "currency": "USD", "amount_usd": "0.35", "at": r.at(), "revision": 0, "final": True})
                else:
                    r.fees[-1].update(amount_usd="0.35", revision=1, final=True, at=r.at())
                r.pending[-1].update(fee_usd="0.35", fee_status="final", net_usd="99.15")
                r.proof()
                account = store.status(path)
                self.assertEqual((account["settled_cash_usd"], account["unsettled_usd"]), ("399.65", "99.15"))
                self.assertEqual(D(account["reserved_cash_usd"]), 0)

    def test_terminal_entry_cancellation_and_projection_commit_atomically(self):
        r = Rehearsal(self.path)
        r.claim()
        r.cancel(r.orders[0])
        self.assertEqual(r.entry_proof()["outcome"], "unresolved")
        with self.assertRaises(ValueError):
            r.claim()
        before = [module.status(self.path) for module in (store, entries, writer, cancellations, controls)]
        r.orders[0]["state"] = "cancelled"
        with contextlib.closing(sqlite3.connect(self.path)) as connection, connection:
            connection.execute("CREATE TRIGGER fail_entry_projection BEFORE INSERT ON reconciliation_events "
                "WHEN NEW.kind='snapshot_applied' BEGIN SELECT RAISE(ABORT,'injected projection failure'); END")
        with self.assertRaises(sqlite3.IntegrityError):
            r.entry_proof()
        self.assertEqual([module.status(self.path) for module in (store, entries, writer, cancellations, controls)], before)
        with contextlib.closing(sqlite3.connect(self.path)) as connection, connection:
            connection.execute("DROP TRIGGER fail_entry_projection")
        self.assertEqual(r.entry_proof()["outcome"], "reconciled")
        self.assertEqual(cancellations.status(self.path)["operations"][0]["state"], "confirmed_cancelled")
        r.claim()
        self.assertEqual(r.allocate("protect", 1, purpose="protective_stop")["outcome"], "reserved")

    def test_stale_evidence_blocks_reduction_but_mapped_cancellation_needs_no_quote(self):
        r = Rehearsal(self.path, quantity=2)
        r.working_stop()
        r.time += timedelta(minutes=2)
        r.claim()
        with self.assertRaises(ValueError):
            r.allocate("stale-exit", 1)
        request = r.cancel(r.orders[1])
        self.assertNotIn("quote_at", request)
        self.assertEqual(r.cancel_adapter.calls, 1)
        self.assertEqual(store.status(self.path)["position_quantity"], 2)
        self.assertEqual(controls.status(self.path)["facts"]["committed_sell_quantity"], 2)

    def test_entry_cancel_resolves_across_entry_to_reducing_evidence_boundary(self):
        r = Rehearsal(self.path)
        r.claim()
        r.allocate("stop", 1, purpose="protective_stop")
        request = r.cancel(r.orders[0])
        self.assertEqual(cancellations.status(self.path)["operations"][0]["target_source"], "entry")
        r.orders[0]["state"] = "cancelled"
        snapshot = r.snapshot()
        result = sells.apply(self.path, snapshot)
        self.assertEqual(result["outcome"], "reconciled")
        self.assertEqual(cancellations.status(self.path)["operations"][0]["state"], "confirmed_cancelled")
        self.assertTrue(sells.apply(self.path, snapshot)["duplicate"])
        self.assertTrue(cancellations.dispatch_synthetic(self.path, request, "accepted", r.cancel_adapter)["duplicate"])
        self.assertEqual(r.cancel_adapter.calls, 1)
        r.claim()
        r.submit("stop", 1, stop=True)
        r.proof()
        self.assertEqual(controls.status(self.path)["facts"]["covered_quantity"], 1)
        self.assertEqual(store.status(self.path)["settled_cash_usd"], "399.65")

    def test_trade_bust_or_position_mismatch_retains_evidence_without_quantity_permission(self):
        for contradiction in ("bust", "quantity"):
            with self.subTest(contradiction=contradiction):
                path = self.path.with_name(contradiction + ".sqlite")
                r = Rehearsal(path, quantity=2)
                r.working_stop()
                r.fill(r.orders[1], 1, fee="0.15")
                r.proof()
                before = store.status(path)
                snapshot = r.snapshot()
                if contradiction == "bust":
                    snapshot["executions"] = snapshot["executions"][:1]
                    snapshot["commissions"] = snapshot["commissions"][:1]
                else:
                    snapshot["positions"][0]["quantity"] = 2
                self.assertEqual(sells.apply(path, snapshot)["outcome"], "unresolved")
                after = store.status(path)
                for key in ("position_quantity", "settled_cash_usd", "unsettled_usd", "attempts"):
                    self.assertEqual(after[key], before[key])
                self.assertTrue(after["blocked"])
                self.assertTrue(writer.status(path)["disarmed"])
                with self.assertRaises(ValueError):
                    r.allocate("unsafe", 1)
                with store.database(path) as connection:
                    self.assertIsNotNone(connection.execute(
                        "SELECT payload FROM reducing_reconciliation_inbox WHERE snapshot_id=?",
                        (snapshot["snapshot_id"],)).fetchone())


if __name__ == "__main__":
    unittest.main()
