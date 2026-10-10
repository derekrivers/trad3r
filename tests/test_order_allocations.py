from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy
import contextlib
import io
import json
from pathlib import Path
import sqlite3
import tempfile
import unittest

from trad3r import order_allocations as allocations
from trad3r import order_reconciliation as reconciliation
from trad3r import order_store as store
from trad3r import order_writer as writer
from trad3r.__main__ import main


class ReducingAllocationTests(unittest.TestCase):
    instrument = "synthetic:NASDAQ:AAPL:USD"

    def setUp(self):
        self.root = tempfile.TemporaryDirectory()
        self.addCleanup(self.root.cleanup)
        self.path = Path(self.root.name) / "orders.sqlite"
        self.prepare_position(self.path)

    def account(self):
        mark = {"equity": "1000", "deposits": "0", "withdrawals": "0"}
        return {
            "schema": "synthetic-order-account-v1", "account_id": "synthetic-test",
            "environment": "synthetic", "at": "2026-09-04T14:00:00Z",
            "settled_cash_usd": "500", "position_quantity": 0, "mark": mark,
            "session_start": mark, "week_start": mark, "ledger_version": 4,
            "risk_version": 7, "evidence_version": 2, "halt_reasons": [],
        }

    def entry(self):
        return {
            "schema": "order-admission-v1", "account_id": "synthetic-test",
            "environment": "synthetic", "intent_id": "entry-intent",
            "candidate_id": "entry-candidate", "client_order_id": "entry-order",
            "decision_at": "2026-09-04T14:00:10Z", "expires_at": "2026-09-04T14:01:00Z",
            "expected_account_version": 0, "expected_ledger_version": 4,
            "expected_risk_version": 7, "expected_evidence_version": 2,
            "expected_policy_sha256": store.digest(store._policy_payload()),
            "instrument_id": self.instrument, "symbol": "AAPL", "currency": "USD",
            "side": "buy", "purpose": "entry", "quantity": 2, "order_type": "limit",
            "time_in_force": "day", "limit_price_usd": "100", "stop_price_usd": "99.5",
            "entry_fee_usd": "0.35", "exit_fee_usd": "0.35",
            "slippage_usd_per_share": "0.05", "usd_to_gbp": "0.8",
            "quote_at": "2026-09-04T14:00:05Z", "fx_at": "2026-09-04T14:00:05Z",
        }

    def prepare_position(self, path, quantity=2):
        allocations.initialize(path, self.account())
        store.admit(path, self.entry())
        writer.claim(path, {
            "schema": "order-writer-claim-v1", "claim_id": "entry-claim",
            "owner_id": "entry-writer", "at": "2026-09-04T14:00:15Z", "expected_epoch": 0,
        })
        submitted = writer.dispatch_synthetic(path, {
            "schema": "order-submission-operation-v1", "operation_id": "entry-submit",
            "intent_id": "entry-intent", "owner_id": "entry-writer", "epoch": 1,
            "at": "2026-09-04T14:00:20Z", "expected_account_version": 1,
        }, "acknowledged")
        broker_id = submitted["submission"]["broker_order_id"]
        execution = {
            "execution_id": "entry-fill", "client_order_id": "entry-order",
            "broker_order_id": broker_id, "instrument_id": self.instrument,
            "symbol": "AAPL", "currency": "USD", "side": "buy", "quantity": quantity,
            "price_usd": "100", "at": "2026-09-04T14:00:30Z",
        }
        fee = {
            "commission_id": "entry-fee", "execution_id": "entry-fill", "currency": "USD",
            "amount_usd": "0.35", "at": "2026-09-04T14:00:31Z", "revision": 0,
        }
        reconciliation.apply(path, {
            "schema": "synthetic-reconciliation-snapshot-v1", "snapshot_id": "entry-snapshot",
            "reconciliation_id": "entry-reconciliation", "account_id": "synthetic-test",
            "environment": "synthetic", "at": "2026-09-04T14:00:40Z",
            "expected_reconciliation_version": 0,
            "completeness": {name: True for name in (
                "orders", "executions", "positions", "currency_cash", "commissions", "settlement")},
            "orders": [{"client_order_id": "entry-order", "broker_order_id": broker_id,
                        "state": "filled" if quantity == 2 else "working",
                        "original_quantity": 2,
                        "cumulative_executed_quantity": quantity}],
            "executions": [execution], "commissions": [fee],
            "currency_cash": {"USD": "299.65" if quantity == 2 else "399.65"},
            "positions": [{"instrument_id": self.instrument, "symbol": "AAPL",
                           "currency": "USD", "quantity": quantity}],
            "unsettled_usd": "0", "pending_settlements": [],
            "mark": {"equity": "699", "deposits": "0", "withdrawals": "0"},
        })
        writer.claim(path, {
            "schema": "order-writer-claim-v1", "claim_id": "management-claim",
            "owner_id": "management-writer", "at": "2026-09-04T14:00:45Z",
            "expected_epoch": 1,
        })

    def request(self, identity="one", quantity=2, fee="0.35", purpose="reducing_exit",
                allocation_version=None, **changes):
        account = store.status(self.path)
        reconciled = reconciliation.status(self.path)
        managed = writer.status(self.path)
        allocation = allocations.status(self.path)
        values = {
            "schema": "reducing-allocation-request-v1",
            "allocation_id": "allocation-" + identity,
            "client_order_id": "reduce-order-" + identity,
            "account_id": "synthetic-test", "environment": "synthetic",
            "entry_intent_id": "entry-intent", "instrument_id": self.instrument,
            "purpose": purpose, "quantity": quantity, "fee_bound_usd": fee,
            "decision_at": "2026-09-04T14:00:50Z",
            "expires_at": "2026-09-04T14:01:35Z",
            "owner_id": "management-writer", "writer_epoch": managed["epoch"],
            "expected_account_version": account["version"],
            "expected_reconciliation_version": reconciled["version"],
            "expected_writer_version": managed["version"],
            "expected_allocation_version": (allocation["version"] if allocation_version is None
                                              else allocation_version),
            "expected_policy_sha256": account["policy_sha256"],
        }
        values.update(changes)
        return values

    def test_v4_starts_explicitly_and_v3_remains_readable_without_migration(self):
        with sqlite3.connect(self.path) as connection:
            self.assertEqual(connection.execute("PRAGMA user_version").fetchone()[0], 4)
        self.assertEqual(allocations.status(self.path)["version"], 0)
        self.assertEqual(store.status(self.path)["position_quantity"], 2)

        old = Path(self.root.name) / "v3.sqlite"
        store.initialize(old, self.account())
        with sqlite3.connect(old) as connection:
            self.assertEqual(connection.execute("PRAGMA user_version").fetchone()[0], 3)
        self.assertEqual(store.status(old)["version"], 0)
        with self.assertRaisesRegex(ValueError, "fresh v4"):
            allocations.status(old)

    def test_explicit_v4_cli_initializes_and_reports_a_disarmed_allocator(self):
        path = Path(self.root.name) / "cli-v4.sqlite"
        snapshot = Path(self.root.name) / "account.json"
        snapshot.write_text(json.dumps(self.account()))
        output = io.StringIO()
        with contextlib.redirect_stdout(output):
            self.assertEqual(main(["order-v4-init", str(path), str(snapshot)]), 0)
        self.assertFalse(json.loads(output.getvalue())["live_trading_enabled"])
        output = io.StringIO()
        with contextlib.redirect_stdout(output):
            self.assertEqual(main(["order-reducing-status", str(path)]), 0)
        report = json.loads(output.getvalue())
        self.assertEqual((report["version"], report["reserved_quantity"]), (0, 0))

    def test_stop_and_exit_share_quantity_and_fee_without_consuming_entry_attempts(self):
        before = store.status(self.path)
        first = allocations.admit(self.path, self.request(
            "stop", quantity=1, fee="0.15", purpose="protective_stop"))
        second = allocations.admit(self.path, self.request(
            "exit", quantity=1, fee="0.20", purpose="reducing_exit"))
        self.assertEqual((first["outcome"], second["outcome"]), ("reserved", "reserved"))
        self.assertEqual((second["reserved_quantity"], second["available_quantity"]), (2, 0))
        self.assertEqual((second["reserved_fee_usd"], second["available_fee_usd"]),
                         ("0.35", "0.00"))
        after = store.status(self.path)
        self.assertEqual((after["attempts"], after["version"], after["assessment"]["halt_reasons"]),
                         (before["attempts"], before["version"], before["assessment"]["halt_reasons"]))
        self.assertIn("daily", after["assessment"]["halt_reasons"])
        self.assertFalse(second["live_trading_enabled"])

    def test_quantity_and_fee_overallocation_are_persistently_rejected(self):
        allocations.admit(self.path, self.request("first", quantity=1, fee="0.20"))
        quantity = allocations.admit(self.path, self.request("quantity", quantity=2, fee="0"))
        fee = allocations.admit(self.path, self.request("fee", quantity=1, fee="0.16"))
        self.assertEqual(quantity["reasons"], ["sell_quantity_unavailable"])
        self.assertEqual(fee["reasons"], ["exit_fee_allowance_unavailable"])
        report = allocations.status(self.path)
        self.assertEqual((report["reserved_quantity"], report["reserved_fee_usd"]), (1, "0.20"))
        self.assertEqual([row["state"] for row in report["allocations"]],
                         ["reserved", "rejected", "rejected"])

    def test_two_full_quantity_concurrent_requests_reserve_exactly_one(self):
        left = self.request("left", allocation_version=0)
        right = self.request("right", allocation_version=0)

        def submit(request):
            try:
                return allocations.admit(self.path, request)["outcome"]
            except ValueError as error:
                self.assertIn("Allocation version changed", str(error))
                return "stale"

        with ThreadPoolExecutor(max_workers=2) as pool:
            outcomes = list(pool.map(submit, (left, right)))
        self.assertCountEqual(outcomes, ["reserved", "stale"])
        report = allocations.status(self.path)
        self.assertEqual((report["reserved_quantity"], report["available_quantity"]), (2, 0))
        self.assertEqual(len(report["allocations"]), 1)

    def test_two_full_fee_requests_cannot_reuse_the_allowance(self):
        first = allocations.admit(self.path, self.request("first", quantity=1, fee="0.35"))
        second = allocations.admit(self.path, self.request("second", quantity=1, fee="0.35"))
        self.assertEqual(first["outcome"], "reserved")
        self.assertEqual(second["outcome"], "rejected")
        self.assertEqual(second["reasons"], ["exit_fee_allowance_unavailable"])
        self.assertEqual(second["reserved_fee_usd"], "0.35")

    def test_verified_partial_entry_can_reserve_only_held_quantity(self):
        path = Path(self.root.name) / "partial.sqlite"
        self.prepare_position(path, quantity=1)
        reserved = allocations.admit(path, self.request_for(path, "partial"))
        self.assertEqual(reserved["outcome"], "rejected")
        self.assertEqual(reserved["reasons"], ["sell_quantity_unavailable"])
        request = self.request_for(path, "stop")
        request.update(quantity=1, purpose="protective_stop",
                       expected_allocation_version=1)
        stop = allocations.admit(path, request)
        self.assertEqual((stop["outcome"], stop["verified_quantity"],
                          stop["reserved_quantity"]), ("reserved", 1, 1))
        self.assertEqual(store.status(path)["attempts"], 1)

    def test_exact_retry_precedes_stale_versions_and_changed_reuse_latches_incident(self):
        request = self.request("same")
        first = allocations.admit(self.path, request)
        duplicate = allocations.admit(self.path, deepcopy(request))
        self.assertTrue(duplicate["duplicate"])
        self.assertEqual(duplicate["allocation"]["committed_version"],
                         first["allocation"]["committed_version"])
        changed = deepcopy(request)
        changed.update(quantity=1, decision_at="2026-09-04T14:00:51Z",
                       expires_at="2026-09-04T14:01:36Z")
        conflict = allocations.admit(self.path, changed)
        self.assertEqual(conflict["outcome"], "identity_conflict")
        self.assertEqual(conflict["unresolved_reasons"], ["allocation_identity_conflict"])
        self.assertTrue(allocations.admit(self.path, deepcopy(changed))["duplicate"])
        with self.assertRaisesRegex(ValueError, "unresolved"):
            allocations.admit(self.path, self.request(
                "later", decision_at="2026-09-04T14:00:52Z",
                expires_at="2026-09-04T14:01:37Z"))

    def test_stale_bindings_and_wrong_writer_fence_write_nothing(self):
        cases = (
            {"expected_account_version": 1},
            {"expected_reconciliation_version": 0},
            {"expected_writer_version": 4},
            {"expected_allocation_version": 1},
            {"writer_epoch": 1},
            {"owner_id": "old-writer"},
            {"expected_policy_sha256": "0" * 64},
        )
        for index, changes in enumerate(cases):
            with self.subTest(changes=changes):
                request = self.request(str(index), **changes)
                with self.assertRaises(ValueError):
                    allocations.admit(self.path, request)
                self.assertEqual(allocations.status(self.path)["version"], 0)

        backwards = self.request("backwards", decision_at="2026-09-04T14:00:39Z",
                                 expires_at="2026-09-04T14:01:20Z")
        with self.assertRaisesRegex(ValueError, "predates current account evidence|move backwards"):
            allocations.admit(self.path, backwards)
        self.assertEqual(allocations.status(self.path)["version"], 0)

    def test_failed_audit_write_rolls_back_reservation(self):
        with sqlite3.connect(self.path) as connection:
            connection.execute(
                "CREATE TRIGGER fail_reducing_audit BEFORE INSERT ON reducing_allocation_audit "
                "BEGIN SELECT RAISE(ABORT, 'injected allocation audit failure'); END")
            connection.commit()
        with self.assertRaises(sqlite3.Error):
            allocations.admit(self.path, self.request())
        report = allocations.status(self.path)
        self.assertEqual((report["version"], report["reserved_quantity"], report["allocations"]),
                         (0, 0, []))

    def test_replay_detects_record_audit_and_projection_damage(self):
        request = self.request()
        allocations.admit(self.path, request)
        mutations = (
            ("UPDATE reducing_allocations SET request_sha256=?", ("0" * 64,)),
            ("UPDATE reducing_allocation_audit SET payload_sha256=?", ("0" * 64,)),
            ("UPDATE reducing_allocation_state SET payload=?", ("replaced-below",)),
        )
        for index, (sql, parameters) in enumerate(mutations):
            with self.subTest(index=index):
                path = Path(self.root.name) / f"damage-{index}.sqlite"
                self.prepare_position(path)
                allocations.admit(path, self.request_for(path, "damage"))
                with sqlite3.connect(path) as connection:
                    if index == 2:
                        raw = connection.execute(
                            "SELECT payload FROM reducing_allocation_state WHERE id=1").fetchone()[0]
                        state = store.decode(raw)
                        state["reserved_quantity"] = 0
                        parameters = (store.pack(state),)
                    connection.execute(sql, parameters)
                    connection.commit()
                for read in (allocations.status, store.status, writer.status,
                             reconciliation.status):
                    with self.subTest(index=index, read=read.__module__ + "." + read.__name__):
                        with self.assertRaises(ValueError):
                            read(path)

    def test_replay_recalculates_each_historical_capacity_decision(self):
        allocations.admit(self.path, self.request("first", quantity=1, fee="0.20"))
        rejected = allocations.admit(self.path, self.request("second", quantity=2, fee="0"))
        self.assertEqual(rejected["state"] if "state" in rejected else rejected["outcome"],
                         "rejected")
        with sqlite3.connect(self.path) as connection:
            raw = connection.execute(
                "SELECT payload FROM reducing_allocations WHERE allocation_id='allocation-second'"
            ).fetchone()[0]
            record = store.decode(raw)
            record["verified_quantity"] = 3
            payload = store.pack(record)
            payload_sha = store.digest(record)
            connection.execute(
                "UPDATE reducing_allocations SET payload=? WHERE allocation_id='allocation-second'",
                (payload,))
            connection.execute(
                "UPDATE reducing_allocation_audit SET payload_sha256=? "
                "WHERE event_key='allocation-second'", (payload_sha,))
            connection.commit()
        with self.assertRaisesRegex(ValueError, "capacity replay"):
            allocations.status(self.path)

    def request_for(self, path, identity):
        original = self.path
        try:
            self.path = path
            return self.request(identity)
        finally:
            self.path = original


if __name__ == "__main__":
    unittest.main()
