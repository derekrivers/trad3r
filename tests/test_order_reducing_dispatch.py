from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy
import sqlite3
import unittest

import test_order_sell_reconciliation as sell_tests
import test_order_allocations as allocation_tests

from trad3r import order_allocations as allocations
from trad3r import order_cancellation as cancellations
from trad3r import order_reconciliation as entry_reconciliation
from trad3r import order_reducing_dispatch as dispatch
from trad3r import order_sell_reconciliation as sells
from trad3r import order_store as store
from trad3r import order_writer as writer


class ReducingDispatchTests(unittest.TestCase):
    def setUp(self):
        self.fixture = sell_tests.SellReconciliationTests(methodName="runTest")
        self.fixture.setUp()
        self.addCleanup(self.fixture.doCleanups)
        self.path = self.fixture.path

    def request(self, operation="dispatch-one", allocation="allocation-exit",
                at="2026-09-04T14:00:55Z", **changes):
        account = store.status(self.path)
        entry = entry_reconciliation.status(self.path)
        reducing = sells.status(self.path)
        managed = writer.status(self.path)
        allocated = allocations.status(self.path)
        cancelled = cancellations.status(self.path)
        dispatched = dispatch.status(self.path)
        value = {
            "schema": "reducing-dispatch-request-v1", "operation_id": operation,
            "allocation_id": allocation, "account_id": "synthetic-test",
            "environment": "synthetic", "owner_id": "management-writer",
            "writer_epoch": managed["epoch"], "at": at,
            "expires_at": "2026-09-04T14:01:30Z", "order_type": "limit",
            "time_in_force": "day", "limit_price_usd": "99.5",
            "stop_price_usd": None, "expected_account_version": account["version"],
            "expected_entry_reconciliation_version": entry["version"],
            "expected_reducing_reconciliation_version": reducing["version"],
            "expected_writer_version": managed["version"],
            "expected_allocation_version": allocated["version"],
            "expected_cancellation_version": cancelled["version"],
            "expected_dispatch_version": dispatched["version"],
        }
        value.update(changes)
        return value

    def correlated_snapshot(self, identity, broker_order_id, state="working",
                            at="2026-09-04T14:01:00Z"):
        snapshot = self.fixture.snapshot(identity, sell_state=state, position=2, at=at)
        snapshot["orders"][1]["order_id"] = broker_order_id
        return snapshot

    def test_acknowledgement_uses_exact_allocated_command_and_requires_reconciliation(self):
        result = dispatch.dispatch_synthetic(self.path, self.request(), "acknowledged")
        operation = result["operation"]
        self.assertEqual(result["outcome"], "acknowledged")
        self.assertEqual((operation["command"]["side"], operation["command"]["quantity"],
                          operation["command"]["purpose"], operation["command"]["order_type"]),
                         ("sell", 2, "reducing_exit", "limit"))
        self.assertFalse(result["live_trading_enabled"])
        self.assertIn("reducing_reconciliation_required", store.status(self.path)["blocked_reasons"])
        self.assertEqual(sells.status(self.path)["committed_sell_quantity"], 0)

    def test_exact_duplicate_and_concurrent_duplicate_call_adapter_once(self):
        adapter = dispatch.SyntheticReducingAdapter()
        request = self.request()
        with ThreadPoolExecutor(max_workers=2) as pool:
            results = list(pool.map(lambda _: dispatch.dispatch_synthetic(
                self.path, deepcopy(request), "acknowledged", adapter), range(2)))
        self.assertEqual(adapter.calls, 1)
        self.assertEqual(sum(row["duplicate"] for row in results), 1)
        duplicate = dispatch.dispatch_synthetic(
            self.path, deepcopy(request), "acknowledged", adapter)
        self.assertTrue(duplicate["duplicate"])
        self.assertEqual(adapter.calls, 1)

    def test_marker_survives_restart_and_never_blindly_retries(self):
        request = self.request()
        marked = dispatch.mark(self.path, request)
        self.assertTrue(marked["should_call_adapter"])
        adapter = dispatch.SyntheticReducingAdapter()
        duplicate = dispatch.dispatch_synthetic(self.path, request, "acknowledged", adapter)
        self.assertTrue(duplicate["duplicate"])
        self.assertEqual(adapter.calls, 0)
        self.assertIn("reducing_submission_pending", writer.status(self.path)["unresolved_reasons"])

    def test_lost_response_and_empty_inventory_retain_full_possible_remainder(self):
        result = dispatch.dispatch_synthetic(self.path, self.request(), "accept_then_timeout")
        self.assertEqual(result["outcome"], "unknown")
        snapshot = self.fixture.snapshot("empty-after-timeout", sell_state="working", position=2)
        snapshot["orders"] = [snapshot["orders"][0]]
        reconciled = sells.apply(self.path, snapshot)
        self.assertEqual((reconciled["verified_quantity"],
                          reconciled["committed_sell_quantity"],
                          reconciled["available_sell_quantity"]), (2, 2, 0))
        self.assertEqual(dispatch.status(self.path)["operations"][0]["state"], "unknown")

    def test_correlated_working_evidence_resolves_submission_uncertainty(self):
        submitted = dispatch.dispatch_synthetic(self.path, self.request(), "acknowledged")
        broker = submitted["operation"]["broker_order_id"]
        reconciled = sells.apply(self.path, self.correlated_snapshot("working", broker))
        self.assertEqual((reconciled["committed_sell_quantity"],
                          reconciled["available_sell_quantity"]), (2, 0))
        operation = dispatch.status(self.path)["operations"][0]
        self.assertEqual((operation["state"], operation["broker_order_id"]), ("working", broker))
        self.assertEqual(dispatch.status(self.path)["unresolved_reasons"], [])

    def test_late_rejection_after_working_evidence_latches_a_conflict(self):
        request = self.request()
        dispatch.mark(self.path, request)
        sells.apply(self.path, self.correlated_snapshot("working-before-result", "synthetic-exit"))
        result = dispatch._record_result(
            self.path, request["operation_id"], request["owner_id"], request["writer_epoch"],
            "2026-09-04T14:01:01Z",
            {"outcome": "rejected", "reason": "synthetic_order_rejected"})
        self.assertEqual(result["operation"]["state"], "conflict")
        self.assertIn("reducing_dispatch_identity_conflict", result["unresolved_reasons"])
        self.assertEqual(sells.status(self.path)["committed_sell_quantity"], 2)

    def test_acknowledged_broker_identity_mismatch_fails_closed(self):
        dispatch.dispatch_synthetic(self.path, self.request(), "acknowledged")
        result = sells.apply(self.path, self.fixture.snapshot(
            "wrong-broker", sell_state="working", position=2))
        self.assertEqual(result["outcome"], "unresolved")
        self.assertIn("order_identity_changed", result["unresolved_reasons"])

    def test_order_without_durable_dispatch_marker_is_external_activity(self):
        snapshot = self.fixture.snapshot("before-dispatch", sell_state="working", position=2,
                                         auto_dispatch=False)
        result = sells.apply(self.path, snapshot)
        self.assertEqual(result["outcome"], "unresolved")
        self.assertIn("sell_before_dispatch", result["unresolved_reasons"])

    def test_protective_allocation_dispatches_only_as_a_stop(self):
        fixture = allocation_tests.ReducingAllocationTests(methodName="runTest")
        fixture.setUp()
        self.addCleanup(fixture.doCleanups)
        original = self.path
        self.path = fixture.path
        try:
            allocation = allocations.admit(
                self.path, fixture.request(purpose="protective_stop"))
            self.assertEqual(allocation["outcome"], "reserved")
            unsafe = self.request(operation="unsafe-stop", allocation="allocation-one",
                                  order_type="stop", limit_price_usd=None,
                                  stop_price_usd="99.4")
            with self.assertRaisesRegex(ValueError, "below the planned stop"):
                dispatch.mark(self.path, unsafe)
            request = self.request(allocation="allocation-one", order_type="stop",
                                   limit_price_usd=None, stop_price_usd="99.5")
            result = dispatch.dispatch_synthetic(self.path, request, "acknowledged")
            self.assertEqual((result["operation"]["command"]["purpose"],
                              result["operation"]["command"]["order_type"],
                              result["operation"]["command"]["stop_price_usd"]),
                             ("protective_stop", "stop", "99.5"))
        finally:
            self.path = original

    def test_definitive_rejection_frees_capacity_only_for_a_new_allocation(self):
        rejected = dispatch.dispatch_synthetic(self.path, self.request(), "rejected")
        self.assertEqual(rejected["outcome"], "rejected")
        self.assertEqual(rejected["unresolved_reasons"], [])
        managed = writer.status(self.path)
        writer.claim(self.path, {"schema": "order-writer-claim-v1",
                                "claim_id": "management-claim-two",
                                "owner_id": "management-writer",
                                "at": "2026-09-04T14:00:57Z",
                                "expected_epoch": managed["epoch"]})
        self.fixture.allocate_exit("allocation-two", "exit-order-two", 2, "0.35",
                                   "2026-09-04T14:00:58Z")
        report = allocations.status(self.path)
        self.assertEqual((report["reserved_quantity"], report["reserved_fee_usd"]), (2, "0.35"))
        self.assertEqual([row["state"] for row in report["allocations"]],
                         ["reserved", "reserved"])

    def test_partial_stop_then_cancel_uses_only_verified_residual_capacity_and_fee(self):
        submitted = dispatch.dispatch_synthetic(self.path, self.request(), "acknowledged")
        broker = submitted["operation"]["broker_order_id"]
        execution = self.fixture.sell_execution(quantity=1)
        execution["order_id"] = broker
        fee = self.fixture.sell_fee(amount="0.15")
        lot = self.fixture.lot(execution, fee="0.15")
        partial = self.fixture.snapshot(
            "partial-before-cancel", [execution], [fee], sell_state="working",
            position=1, pending=[lot], at="2026-09-04T14:01:00Z")
        partial["orders"][1]["order_id"] = broker
        sells.apply(self.path, partial)

        managed = writer.status(self.path)
        writer.claim(self.path, {"schema": "order-writer-claim-v1",
                                "claim_id": "cancel-after-partial",
                                "owner_id": "cancel-writer",
                                "at": "2026-09-04T14:01:01Z",
                                "expected_epoch": managed["epoch"]})
        account, entry, reducing, managed, allocated, cancelled = (
            store.status(self.path), entry_reconciliation.status(self.path),
            sells.status(self.path), writer.status(self.path), allocations.status(self.path),
            cancellations.status(self.path))
        cancel = {
            "schema": "order-cancellation-request-v1", "operation_id": "cancel-partial",
            "account_id": "synthetic-test", "environment": "synthetic",
            "target_client_order_id": "exit-order", "target_order_id": broker,
            "owner_id": "cancel-writer", "writer_epoch": managed["epoch"],
            "at": "2026-09-04T14:01:02Z", "expires_at": "2026-09-04T14:01:30Z",
            "expected_account_version": account["version"],
            "expected_entry_reconciliation_version": entry["version"],
            "expected_reducing_reconciliation_version": reducing["version"],
            "expected_writer_version": managed["version"],
            "expected_allocation_version": allocated["version"],
            "expected_cancellation_version": cancelled["version"],
        }
        cancellations.dispatch_synthetic(self.path, cancel, "accepted")
        terminal = self.fixture.snapshot(
            "cancelled-after-partial", [execution], [fee], sell_state="cancelled",
            position=1, pending=[lot], at="2026-09-04T14:01:05Z")
        terminal["orders"][1]["order_id"] = broker
        sells.apply(self.path, terminal)
        self.assertEqual(dispatch.status(self.path)["operations"][0]["state"], "cancelled")

        managed = writer.status(self.path)
        writer.claim(self.path, {"schema": "order-writer-claim-v1",
                                "claim_id": "residual-exit-claim",
                                "owner_id": "management-writer",
                                "at": "2026-09-04T14:01:06Z",
                                "expected_epoch": managed["epoch"]})
        self.fixture.allocate_exit("allocation-two", "exit-order-two", 1, "0.20",
                                   "2026-09-04T14:01:07Z")
        allocated = allocations.status(self.path)
        self.assertEqual((allocated["verified_quantity"], allocated["reserved_quantity"],
                          allocated["reserved_fee_usd"], allocated["available_fee_usd"]),
                         (1, 1, "0.35", "0.00"))
        second = dispatch.dispatch_synthetic(
            self.path, self.request("dispatch-two", "allocation-two",
                                    "2026-09-04T14:01:08Z"), "acknowledged")
        self.assertEqual(second["operation"]["command"]["quantity"], 1)

    def test_changed_operation_identity_latches_without_adapter_call(self):
        adapter = dispatch.SyntheticReducingAdapter()
        request = self.request()
        dispatch.dispatch_synthetic(self.path, request, "acknowledged", adapter)
        changed = deepcopy(request)
        changed["limit_price_usd"] = "99.4"
        conflict = dispatch.mark(self.path, changed)
        self.assertEqual(conflict["outcome"], "identity_conflict")
        self.assertIn("reducing_dispatch_identity_conflict", conflict["unresolved_reasons"])
        self.assertEqual(adapter.calls, 1)

    def test_stale_versions_expiry_prices_and_fence_fail_before_marker(self):
        cases = []
        for field in ("expected_account_version", "expected_entry_reconciliation_version",
                      "expected_reducing_reconciliation_version", "expected_writer_version",
                      "expected_allocation_version", "expected_cancellation_version",
                      "expected_dispatch_version"):
            request = self.request(operation="stale-" + field)
            request[field] += 1
            cases.append(request)
        cases.append(self.request(operation="stale-epoch", writer_epoch=0))
        cases.append(self.request(operation="market", order_type="market",
                                  limit_price_usd=None))
        cases.append(self.request(operation="expired", at="2026-09-04T14:01:40Z",
                                  expires_at="2026-09-04T14:01:50Z"))
        for request in cases:
            with self.subTest(operation=request["operation_id"]):
                with self.assertRaises(ValueError):
                    dispatch.mark(self.path, request)
        self.assertEqual(dispatch.status(self.path)["operations"], [])

    def test_result_commit_failure_retains_marker_and_corruption_blocks_reads(self):
        request = self.request()
        dispatch.mark(self.path, request)
        connection = sqlite3.connect(self.path)
        connection.execute("CREATE TRIGGER fail_dispatch_result BEFORE UPDATE ON "
                           "reducing_dispatch_operations BEGIN SELECT RAISE(ABORT, 'injected'); END")
        connection.commit()
        connection.close()
        with self.assertRaises(sqlite3.IntegrityError):
            dispatch._record_result(self.path, request["operation_id"], request["owner_id"],
                                    request["writer_epoch"], request["at"],
                                    {"outcome": "acknowledged", "broker_order_id": "broker-one"})
        self.assertEqual(dispatch.status(self.path)["operations"][0]["state"], "submitting")
        connection = sqlite3.connect(self.path)
        connection.execute("DROP TRIGGER fail_dispatch_result")
        connection.execute("UPDATE reducing_dispatch_events SET payload_sha256='bad' WHERE sequence=1")
        connection.commit()
        connection.close()
        with self.assertRaisesRegex(ValueError, "Invalid reducing dispatch event"):
            store.status(self.path)


if __name__ == "__main__":
    unittest.main()
