from copy import deepcopy
from concurrent.futures import ThreadPoolExecutor
import contextlib
import io
import json
from pathlib import Path
import sqlite3
import unittest

import test_order_sell_reconciliation as sell_tests
import test_order_allocations as allocation_tests

from trad3r import order_reconciliation as entry_reconciliation
from trad3r import order_cancellation as cancellations
from trad3r import order_sell_reconciliation as sells
from trad3r import order_store as store
from trad3r import order_writer as writer
from trad3r.__main__ import main


class CancellationTests(unittest.TestCase):
    def setUp(self):
        self.fixture = sell_tests.SellReconciliationTests(methodName="runTest")
        self.fixture.setUp()
        self.addCleanup(self.fixture.doCleanups)
        self.path = self.fixture.path
        sells.apply(self.path, self.fixture.snapshot(
            "working-before-cancel", sell_state="working", position=2,
            at="2026-09-04T14:01:00Z"))
        managed = writer.status(self.path)
        writer.claim(self.path, {
            "schema": "order-writer-claim-v1", "claim_id": "cancel-claim",
            "owner_id": "cancel-writer", "at": "2026-09-04T14:01:01Z",
            "expected_epoch": managed["epoch"],
        })

    def request(self, operation="cancel-one", at="2026-09-04T14:01:03Z"):
        with store.database(self.path) as connection:
            account = store._read_state(connection)
            entry = __import__("trad3r.order_reconciliation", fromlist=["_read"])._read(connection)[0]
            reducing = sells._read(connection)[0]
            managed = writer._read_writer(connection)[0]
            allocation = __import__("trad3r.order_allocations", fromlist=["_read"])._read(connection)[0]
            cancellation = cancellations._read(connection)[0]
        return {
            "schema": "order-cancellation-request-v1", "operation_id": operation,
            "account_id": "synthetic-test", "environment": "synthetic",
            "target_client_order_id": "exit-order", "target_order_id": "synthetic-exit",
            "owner_id": "cancel-writer", "writer_epoch": managed["epoch"],
            "at": at, "expires_at": "2026-09-04T14:01:30Z",
            "expected_account_version": account["version"],
            "expected_entry_reconciliation_version": entry["version"],
            "expected_reducing_reconciliation_version": reducing["version"],
            "expected_writer_version": managed["version"],
            "expected_allocation_version": allocation["version"],
            "expected_cancellation_version": cancellation["version"],
        }

    def test_acceptance_retains_every_resource_until_cancelled_evidence(self):
        before = store.status(self.path)
        result = cancellations.dispatch_synthetic(self.path, self.request(), "accepted")
        self.assertEqual(result["outcome"], "accepted")
        self.assertEqual((result["quantity_released"], result["cash_released_usd"],
                          result["risk_released_gbp"]), (0, "0", "0"))
        pending = store.status(self.path)
        self.assertEqual((pending["position_quantity"], pending["reserved_cash_usd"],
                          pending["reserved_exposure_gbp"], pending["reserved_loss_gbp"]),
                         (before["position_quantity"], before["reserved_cash_usd"],
                          before["reserved_exposure_gbp"], before["reserved_loss_gbp"]))
        self.assertIn("cancellation_reconciliation_required", pending["blocked_reasons"])

        reconciled = sells.apply(self.path, self.fixture.snapshot(
            "cancelled-proof", sell_state="cancelled", position=2,
            at="2026-09-04T14:01:05Z"))
        self.assertEqual((reconciled["verified_quantity"],
                          reconciled["committed_sell_quantity"],
                          reconciled["available_sell_quantity"]), (2, 0, 2))
        operation = cancellations.status(self.path)["operations"][0]
        self.assertEqual(operation["state"], "confirmed_cancelled")
        self.assertEqual(operation["adapter_result"]["outcome"], "accepted")

    def test_fill_before_response_makes_cancel_moot_and_retains_response(self):
        request = self.request()
        marked = cancellations.mark(self.path, request)
        self.assertTrue(marked["should_call_adapter"])
        execution = self.fixture.sell_execution()
        fee = self.fixture.sell_fee()
        sells.apply(self.path, self.fixture.snapshot(
            "fill-before-response", [execution], [fee], position=0,
            pending=[self.fixture.lot(execution)], at="2026-09-04T14:01:05Z"))
        self.assertEqual(cancellations.status(self.path)["operations"][0]["state"], "moot_filled")
        result = cancellations._record_result(
            self.path, request["operation_id"], request["owner_id"], request["writer_epoch"],
            "2026-09-04T14:01:06Z", {"outcome": "accepted", "receipt_id": "late-receipt"})
        self.assertEqual(result["outcome"], "moot_filled")
        self.assertEqual(result["operation"]["adapter_result"]["receipt_id"], "late-receipt")
        self.assertEqual(store.status(self.path)["position_quantity"], 0)

    def test_partial_sell_during_cancel_keeps_residual_commitment(self):
        result = cancellations.dispatch_synthetic(self.path, self.request(), "accepted")
        self.assertEqual(result["outcome"], "accepted")
        execution = self.fixture.sell_execution(quantity=1)
        reconciled = sells.apply(self.path, self.fixture.snapshot(
            "partial-during-cancel", [execution], [self.fixture.sell_fee(amount="0.15")],
            sell_state="working", position=1, pending=[self.fixture.lot(execution, fee="0.15")],
            at="2026-09-04T14:01:05Z"))
        self.assertEqual((reconciled["verified_quantity"],
                          reconciled["committed_sell_quantity"],
                          reconciled["available_sell_quantity"]), (1, 1, 0))
        operation = cancellations.status(self.path)["operations"][0]
        self.assertEqual(operation["state"], "accepted")
        self.assertIn("cancellation_reconciliation_required",
                      cancellations.status(self.path)["unresolved_reasons"])

    def test_partial_entry_fill_during_cancel_then_completion_is_moot(self):
        partial = allocation_tests.ReducingAllocationTests(methodName="runTest")
        partial.root = self.fixture.root
        partial.path = self.fixture.path.parent / "partial-entry-cancel.sqlite"
        partial.prepare_position(partial.path, quantity=1)
        original_path = self.path
        self.path = partial.path
        try:
            projection = entry_reconciliation.status(self.path)["order_projection"]
            request = self.request("cancel-entry", "2026-09-04T14:00:47Z")
            request.update(target_client_order_id="entry-order",
                           target_order_id=projection["broker_order_id"],
                           owner_id="management-writer",
                           expires_at="2026-09-04T14:01:20Z")
            marked = cancellations.mark(self.path, request)
            self.assertEqual(marked["outcome"], "cancel_pending")

            current = entry_reconciliation.status(self.path)
            entry_reconciliation.apply(self.path, {
                "schema": "synthetic-reconciliation-snapshot-v1",
                "snapshot_id": "entry-fill-after-cancel",
                "reconciliation_id": "entry-reconciliation-after-cancel",
                "account_id": "synthetic-test", "environment": "synthetic",
                "at": "2026-09-04T14:00:50Z",
                "expected_reconciliation_version": current["version"],
                "completeness": {name: True for name in (
                    "orders", "executions", "positions", "currency_cash", "commissions", "settlement")},
                "orders": [{"client_order_id": "entry-order",
                            "broker_order_id": projection["broker_order_id"], "state": "filled",
                            "original_quantity": 2, "cumulative_executed_quantity": 2}],
                "executions": [
                    {"execution_id": "entry-fill", "client_order_id": "entry-order",
                     "broker_order_id": projection["broker_order_id"],
                     "instrument_id": partial.instrument, "symbol": "AAPL", "currency": "USD",
                     "side": "buy", "quantity": 1, "price_usd": "100",
                     "at": "2026-09-04T14:00:30Z"},
                    {"execution_id": "entry-fill-two", "client_order_id": "entry-order",
                     "broker_order_id": projection["broker_order_id"],
                     "instrument_id": partial.instrument, "symbol": "AAPL", "currency": "USD",
                     "side": "buy", "quantity": 1, "price_usd": "100",
                     "at": "2026-09-04T14:00:48Z"},
                ],
                "commissions": [
                    {"commission_id": "entry-fee", "execution_id": "entry-fill",
                     "currency": "USD", "amount_usd": "0.35",
                     "at": "2026-09-04T14:00:31Z", "revision": 0},
                    {"commission_id": "entry-fee-two", "execution_id": "entry-fill-two",
                     "currency": "USD", "amount_usd": "0",
                     "at": "2026-09-04T14:00:49Z", "revision": 0},
                ],
                "currency_cash": {"USD": "299.65"},
                "positions": [{"instrument_id": partial.instrument, "symbol": "AAPL",
                               "currency": "USD", "quantity": 2}],
                "unsettled_usd": "0", "pending_settlements": [],
                "mark": {"equity": "699", "deposits": "0", "withdrawals": "0"},
            })
            self.assertEqual(cancellations.status(self.path)["operations"][0]["state"],
                             "moot_filled")
            self.assertEqual(store.status(self.path)["position_quantity"], 2)
        finally:
            self.path = original_path

    def test_rejected_working_and_bare_denial_have_distinct_safety_states(self):
        rejected = cancellations.dispatch_synthetic(
            self.path, self.request(), "rejected_working")
        self.assertEqual(rejected["outcome"], "rejected_working")
        self.assertEqual(rejected["unresolved_reasons"], [])

        # A fresh fenced owner may make a later attempt after confirmed working evidence.
        managed = writer.status(self.path)
        writer.claim(self.path, {
            "schema": "order-writer-claim-v1", "claim_id": "cancel-claim-two",
            "owner_id": "cancel-writer", "at": "2026-09-04T14:01:07Z",
            "expected_epoch": managed["epoch"],
        })
        denied = cancellations.dispatch_synthetic(
            self.path, self.request("cancel-two", "2026-09-04T14:01:08Z"), "denied")
        self.assertEqual(denied["outcome"], "unknown")
        self.assertEqual(denied["unresolved_reasons"], ["cancellation_unknown"])
        self.assertEqual(store.status(self.path)["position_quantity"], 2)
        self.assertEqual(sells.status(self.path)["committed_sell_quantity"], 2)

        sells.apply(self.path, self.fixture.snapshot(
            "working-after-denial", sell_state="working", position=2,
            at="2026-09-04T14:01:10Z"))
        operations = {row["operation_id"]: row for row in cancellations.status(self.path)["operations"]}
        self.assertEqual(operations["cancel-two"]["state"], "rejected_working")
        self.assertEqual(cancellations.status(self.path)["unresolved_reasons"], [])

    def test_exact_duplicate_never_calls_adapter_twice_and_changed_identity_latches(self):
        adapter = cancellations.SyntheticCancellationAdapter()
        request = self.request()
        cancellations.dispatch_synthetic(self.path, request, "accepted", adapter)
        duplicate = cancellations.dispatch_synthetic(self.path, deepcopy(request), "accepted", adapter)
        self.assertTrue(duplicate["duplicate"])
        self.assertEqual(adapter.calls, 1)
        changed = deepcopy(request)
        changed["target_order_id"] = "changed-order"
        conflict = cancellations.mark(self.path, changed)
        self.assertEqual(conflict["outcome"], "identity_conflict")
        self.assertIn("cancellation_identity_conflict", conflict["unresolved_reasons"])
        self.assertEqual(cancellations.status(self.path)["incident_count"], 1)

    def test_concurrent_exact_requests_make_one_adapter_call(self):
        adapter = cancellations.SyntheticCancellationAdapter()
        request = self.request()
        with ThreadPoolExecutor(max_workers=2) as pool:
            results = list(pool.map(
                lambda _: cancellations.dispatch_synthetic(
                    self.path, deepcopy(request), "accepted", adapter), range(2)))
        self.assertEqual(adapter.calls, 1)
        self.assertEqual(sum(result["duplicate"] for result in results), 1)
        self.assertEqual(len(cancellations.status(self.path)["operations"]), 1)

    def test_marker_survives_restart_and_prevents_blind_adapter_retry(self):
        request = self.request()
        cancellations.mark(self.path, request)
        self.assertEqual(cancellations.status(self.path)["operations"][0]["state"], "cancel_pending")
        adapter = cancellations.SyntheticCancellationAdapter()
        duplicate = cancellations.dispatch_synthetic(self.path, request, "accepted", adapter)
        self.assertTrue(duplicate["duplicate"])
        self.assertEqual(adapter.calls, 0)
        self.assertIn("cancellation_pending", writer.status(self.path)["unresolved_reasons"])

    def test_result_commit_failure_rolls_back_and_replay_corruption_fails_closed(self):
        request = self.request()
        cancellations.mark(self.path, request)
        connection = sqlite3.connect(self.path)
        connection.execute("CREATE TRIGGER fail_cancel_result BEFORE UPDATE ON cancellation_operations "
                           "BEGIN SELECT RAISE(ABORT, 'injected'); END")
        connection.commit()
        connection.close()
        with self.assertRaises(sqlite3.IntegrityError):
            cancellations._record_result(
                self.path, request["operation_id"], request["owner_id"], request["writer_epoch"],
                request["at"], {"outcome": "accepted", "receipt_id": "receipt"})
        self.assertEqual(cancellations.status(self.path)["operations"][0]["state"], "cancel_pending")
        connection = sqlite3.connect(self.path)
        connection.execute("DROP TRIGGER fail_cancel_result")
        connection.execute("UPDATE cancellation_events SET payload_sha256='bad' WHERE sequence=1")
        connection.commit()
        connection.close()
        with self.assertRaisesRegex(ValueError, "Invalid cancellation event|Protection source digest mismatch"):
            store.status(self.path)

    def test_sql_identity_corruption_blocks_all_account_reads(self):
        cancellations.mark(self.path, self.request())
        connection = sqlite3.connect(self.path)
        connection.execute("UPDATE cancellation_operations SET target_order_id='forged'")
        connection.commit()
        connection.close()
        with self.assertRaisesRegex(ValueError, "SQL identity mismatch"):
            store.status(self.path)

    def test_stale_fencing_versions_expiry_and_unknown_target_fail_before_marker(self):
        cases = []
        stale_epoch = self.request("stale-epoch")
        stale_epoch["writer_epoch"] -= 1
        cases.append(stale_epoch)
        stale_version = self.request("stale-version")
        stale_version["expected_account_version"] += 1
        cases.append(stale_version)
        for field in ("expected_entry_reconciliation_version",
                      "expected_reducing_reconciliation_version",
                      "expected_writer_version", "expected_allocation_version",
                      "expected_cancellation_version"):
            changed = self.request("stale-" + field.removeprefix("expected_").replace("_", "-"))
            changed[field] += 1
            cases.append(changed)
        wrong_owner = self.request("wrong-owner")
        wrong_owner["owner_id"] = "prior-owner"
        cases.append(wrong_owner)
        expired = self.request("expired")
        expired["expires_at"] = expired["at"]
        cases.append(expired)
        unknown = self.request("unknown")
        unknown["target_order_id"] = "absent"
        cases.append(unknown)
        for request in cases:
            with self.subTest(operation=request["operation_id"]):
                with self.assertRaises(ValueError):
                    cancellations.mark(self.path, request)
        self.assertEqual(cancellations.status(self.path)["operations"], [])
        self.assertFalse(writer.status(self.path)["disarmed"])

    def test_cli_is_synthetic_readable_and_v3_has_no_cancellation_surface(self):
        request_path = Path(self.fixture.root.name) / "cancel.json"
        request_path.write_text(json.dumps(self.request()))
        output = io.StringIO()
        with contextlib.redirect_stdout(output):
            self.assertEqual(main(["order-cancel-synthetic", str(self.path), str(request_path),
                                   "--outcome", "accept_then_timeout"]), 0)
        report = json.loads(output.getvalue())
        self.assertEqual(report["outcome"], "unknown")
        self.assertFalse(report["live_trading_enabled"])
        for command in ("order-cancel-status", "order-cancel-history"):
            output = io.StringIO()
            with contextlib.redirect_stdout(output):
                self.assertEqual(main([command, str(self.path)]), 0)
            self.assertNotIn("live_trading_enabled\": true", output.getvalue())

        old = Path(self.fixture.root.name) / "v3.sqlite"
        store.initialize(old, self.fixture.account())
        with self.assertRaisesRegex(ValueError, "fresh v4"):
            cancellations.status(old)


if __name__ == "__main__":
    unittest.main()
