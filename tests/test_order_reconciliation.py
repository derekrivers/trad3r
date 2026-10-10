from copy import deepcopy
import contextlib
import io
import json
from pathlib import Path
import sqlite3
import tempfile
import unittest

from trad3r import order_reconciliation as reconciliation
from trad3r import order_store as store
from trad3r import order_writer as writer
from trad3r.__main__ import main


class OrderReconciliationTests(unittest.TestCase):
    def setUp(self):
        self.root = tempfile.TemporaryDirectory()
        self.addCleanup(self.root.cleanup)
        self.path = Path(self.root.name) / "orders.sqlite"
        store.initialize(self.path, self.account())
        store.admit(self.path, self.proposal())

    def account(self):
        mark = {"equity": "1000", "deposits": "0", "withdrawals": "0"}
        return {
            "schema": "synthetic-order-account-v1", "account_id": "synthetic-test",
            "environment": "synthetic", "at": "2026-09-04T14:00:00Z",
            "settled_cash_usd": "500", "position_quantity": 0, "mark": mark,
            "session_start": mark, "week_start": mark, "ledger_version": 4,
            "risk_version": 7, "evidence_version": 2, "halt_reasons": [],
        }

    def proposal(self):
        return {
            "schema": "order-admission-v1", "account_id": "synthetic-test",
            "environment": "synthetic", "intent_id": "intent-one",
            "candidate_id": "candidate-one", "client_order_id": "order-one",
            "decision_at": "2026-09-04T14:00:30Z", "expires_at": "2026-09-04T14:01:15Z",
            "expected_account_version": 0, "expected_ledger_version": 4,
            "expected_risk_version": 7, "expected_evidence_version": 2,
            "expected_policy_sha256": store.digest(store._policy_payload()),
            "instrument_id": "synthetic:NASDAQ:AAPL:USD", "symbol": "AAPL",
            "currency": "USD", "side": "buy", "purpose": "entry", "quantity": 2,
            "order_type": "limit", "time_in_force": "day", "limit_price_usd": "100",
            "stop_price_usd": "99.5", "entry_fee_usd": "0.35", "exit_fee_usd": "0.35",
            "slippage_usd_per_share": "0.05", "usd_to_gbp": "0.8",
            "quote_at": "2026-09-04T14:00:15Z", "fx_at": "2026-09-04T14:00:15Z",
        }

    def claim(self, identity="one", epoch=0, at="2026-09-04T14:00:35Z"):
        return {"schema": "order-writer-claim-v1", "claim_id": "claim-" + identity,
                "owner_id": "writer-a", "at": at, "expected_epoch": epoch}

    def operation(self):
        return {"schema": "order-submission-operation-v1", "operation_id": "submit-one",
                "intent_id": "intent-one", "owner_id": "writer-a", "epoch": 1,
                "at": "2026-09-04T14:00:40Z", "expected_account_version": 1}

    def submitted(self, outcome="acknowledged"):
        writer.claim(self.path, self.claim())
        return writer.dispatch_synthetic(self.path, self.operation(), outcome)

    def execution(self, identity, quantity, price, at):
        return {"execution_id": identity, "client_order_id": "order-one",
                "broker_order_id": self.broker_id, "instrument_id": "synthetic:NASDAQ:AAPL:USD",
                "symbol": "AAPL", "currency": "USD", "side": "buy", "quantity": quantity,
                "price_usd": price, "at": at}

    def fee(self, identity, execution, amount, at):
        return {"commission_id": identity, "execution_id": execution, "currency": "USD",
                "amount_usd": amount, "at": at, "revision": 0}

    def snapshot(self, identity="one", version=0, at="2026-09-04T14:00:50Z",
                 state="working", executions=None, commissions=None, cash="500",
                 position=0, include_order=True, complete=True, mark=None):
        executions = executions or []
        commissions = commissions or []
        order = {"client_order_id": "order-one", "broker_order_id": self.broker_id,
                 "state": state, "original_quantity": 2,
                 "cumulative_executed_quantity": sum(row["quantity"] for row in executions)}
        positions = [] if position == 0 else [{
            "instrument_id": "synthetic:NASDAQ:AAPL:USD", "symbol": "AAPL",
            "currency": "USD", "quantity": position}]
        return {
            "schema": "synthetic-reconciliation-snapshot-v1", "snapshot_id": "snapshot-" + identity,
            "reconciliation_id": "reconciliation-" + identity,
            "account_id": "synthetic-test", "environment": "synthetic", "at": at,
            "expected_reconciliation_version": version,
            "completeness": {name: complete for name in (
                "orders", "executions", "positions", "currency_cash", "commissions", "settlement")},
            "orders": [order] if include_order else [], "executions": executions,
            "commissions": commissions, "currency_cash": {"USD": cash},
            "positions": positions, "unsettled_usd": "0", "pending_settlements": [],
            "mark": mark or {"equity": "1000", "deposits": "0", "withdrawals": "0"},
        }

    def test_complete_working_order_resolves_and_preserves_entry_reservation(self):
        result = self.submitted()
        self.broker_id = result["submission"]["broker_order_id"]
        applied = reconciliation.apply(self.path, self.snapshot())
        self.assertEqual(applied["outcome"], "reconciled")
        self.assertEqual(applied["order_projection"]["state"], "working")
        self.assertEqual(store.status(self.path)["reserved_cash_usd"], "200.80")
        report = writer.status(self.path)
        self.assertTrue(report["disarmed"])
        self.assertEqual(report["unresolved_reasons"], [])
        claimed = writer.claim(self.path, self.claim("next", epoch=1, at="2026-09-04T14:00:55Z"))
        self.assertEqual(claimed["epoch"], 2)

    def test_empty_snapshot_checks_cash_and_both_settlement_fields(self):
        self.broker_id = None
        cases = [({"currency_cash": {"USD": "499"}}, "currency_cash_mismatch"),
                 ({"unsettled_usd": "1"}, "settlement_mismatch"),
                 ({"pending_settlements": [{"amount_usd": "1"}]}, "settlement_mismatch")]
        for index, (changed, reason) in enumerate(cases):
            with self.subTest(changed=changed):
                snapshot = self.snapshot(str(index), version=index, include_order=False)
                snapshot.update(changed)
                report = reconciliation.apply(self.path, snapshot)
                self.assertEqual(report["outcome"], "unresolved")
                self.assertIn(reason, report["unresolved_reasons"])
                self.assertIn(reason, store.status(self.path)["blocked_reasons"])
                self.assertEqual(store.status(self.path)["version"], 1)
                self.assertTrue(writer.status(self.path)["disarmed"])

    def test_empty_snapshot_persists_marks_halts_and_unsent_reservations(self):
        self.broker_id = None
        for admitted in (False, True):
            with self.subTest(admitted=admitted):
                path = Path(self.root.name) / f"empty-{admitted}.sqlite"
                store.initialize(path, self.account())
                if admitted:
                    store.admit(path, self.proposal())
                before = store.status(path)
                snapshot = self.snapshot(include_order=False, mark={
                    "equity": "699", "deposits": "0", "withdrawals": "0"})
                result = reconciliation.apply(path, snapshot)
                self.assertEqual(result["outcome"], "reconciled")
                account = store.status(path)
                self.assertEqual(account["version"], before["version"] + 1)
                self.assertEqual(account["as_of"], "2026-09-04T14:00:50+00:00")
                self.assertEqual(account["assessment"]["halt_reasons"],
                                 ("daily", "overall", "weekly"))
                for field in ("reserved_cash_usd", "reserved_exposure_gbp", "reserved_loss_gbp",
                              "attempts", "session", "week"):
                    self.assertEqual(account[field], before[field])
                self.assertTrue(reconciliation.apply(path, deepcopy(snapshot))["duplicate"])
                self.assertEqual(store.status(path)["version"], account["version"])
                recovered = self.snapshot("recovered", version=1, include_order=False,
                                          at="2026-09-04T14:01:00Z")
                reconciliation.apply(path, recovered)
                self.assertEqual(store.status(path)["assessment"]["halt_reasons"],
                                 ("daily", "overall", "weekly"))
                self.assertEqual(writer.status(path)["submissions"], [])
                if admitted:
                    writer.claim(path, self.claim(at="2026-09-04T14:01:01Z"))
                    operation = self.operation()
                    operation.update(at="2026-09-04T14:01:02Z",
                                     expected_account_version=store.status(path)["version"])
                    with self.assertRaisesRegex(ValueError, "halted"):
                        writer.mark_submission(path, operation)

    def test_empty_snapshot_failure_rolls_back_account_mark_and_inbox(self):
        self.broker_id = None
        before = store.status(self.path)
        with contextlib.closing(sqlite3.connect(self.path)) as connection:
            connection.execute(
                "CREATE TRIGGER fail_disarm BEFORE INSERT ON writer_events "
                "BEGIN SELECT RAISE(ABORT, 'injected disarm failure'); END")
            connection.commit()
        with self.assertRaises(sqlite3.Error):
            reconciliation.apply(self.path, self.snapshot(include_order=False, mark={
                "equity": "699", "deposits": "0", "withdrawals": "0"}))
        self.assertEqual(store.status(self.path), before)
        self.assertEqual(reconciliation.status(self.path)["inbox_count"], 0)
        self.assertEqual(reconciliation.history(self.path), [])
        self.assertEqual(writer.status(self.path)["version"], 0)

    def test_account_only_adjustment_cannot_release_an_intent_during_replay(self):
        self.broker_id = None
        result = reconciliation.apply(self.path, self.snapshot(include_order=False))
        adjustment = result["adjustment"]
        self.assertIsNone(adjustment["intent_id"])
        adjustment["reserved_cash_usd"] = "0"
        with contextlib.closing(sqlite3.connect(self.path)) as connection:
            connection.execute("UPDATE reconciliation_adjustments SET payload=?",
                               (store.pack(adjustment),))
            connection.execute("UPDATE audit SET payload_sha256=? WHERE kind='reconciliation'",
                               (store.digest(adjustment),))
            state = json.loads(connection.execute(
                "SELECT payload FROM account_state WHERE id=1").fetchone()[0])
            state["reserved_cash_usd"] = "0"
            connection.execute("UPDATE account_state SET payload=? WHERE id=1", (store.pack(state),))
            connection.commit()
        with self.assertRaisesRegex(ValueError, "another intent's reservation"):
            store.status(self.path)

    def reserve_second(self):
        proposal = self.proposal()
        proposal.update(intent_id="intent-two", candidate_id="candidate-two",
                        client_order_id="order-two", expected_account_version=2,
                        decision_at="2026-09-04T14:00:51Z", expires_at="2026-09-04T14:01:20Z",
                        quote_at="2026-09-04T14:00:45Z", fx_at="2026-09-04T14:00:45Z")
        self.assertEqual(store.admit(self.path, proposal)["outcome"], "reserved")

    def test_old_rejection_snapshot_preserves_new_unsent_reservation(self):
        self.submitted("rejected")
        self.broker_id = None
        reconciliation.apply(self.path, self.snapshot(state="rejected"))
        self.reserve_second()
        before = store.status(self.path)
        report = reconciliation.apply(self.path, self.snapshot(
            "old-again", version=1, state="rejected", at="2026-09-04T14:00:55Z"))
        self.assertEqual(report["outcome"], "reconciled")
        after = store.status(self.path)
        for field in ("reserved_cash_usd", "reserved_exposure_gbp", "reserved_loss_gbp", "attempts"):
            self.assertEqual(after[field], before[field])
        writer.claim(self.path, self.claim("two", epoch=1, at="2026-09-04T14:00:56Z"))
        operation = self.operation()
        operation.update(operation_id="submit-two", intent_id="intent-two", epoch=2,
                         at="2026-09-04T14:00:57Z", expected_account_version=after["version"])
        self.assertEqual(writer.dispatch_synthetic(self.path, operation, "acknowledged")["outcome"],
                         "acknowledged")

    def test_late_fill_cannot_replace_a_newer_entry_reservation(self):
        self.broker_id = self.submitted()["submission"]["broker_order_id"]
        reconciliation.apply(self.path, self.snapshot(state="cancelled"))
        self.reserve_second()
        before = store.status(self.path)
        execution = self.execution("late", 2, "100", "2026-09-04T14:00:52Z")
        snapshot = self.snapshot("late", version=1, at="2026-09-04T14:00:55Z", state="filled",
                                 executions=[execution], cash="300", position=2)
        result = reconciliation.apply(self.path, snapshot)
        self.assertIn("reservation_owner_conflict", result["unresolved_reasons"])
        self.assertEqual(result["outcome"], "unresolved")
        after = store.status(self.path)
        for field in ("version", "settled_cash_usd", "position_quantity", "reserved_cash_usd",
                      "reserved_exposure_gbp", "reserved_loss_gbp"):
            self.assertEqual(after[field], before[field])
        self.assertTrue(writer.status(self.path)["disarmed"])
        corrected = self.snapshot("corrected", version=2, at="2026-09-04T14:00:56Z",
                                  state="cancelled")
        self.assertIn("reservation_owner_conflict",
                      reconciliation.apply(self.path, corrected)["unresolved_reasons"])

    def expire_unsent(self):
        writer.claim(self.path, self.claim())
        operation = self.operation()
        operation["at"] = "2026-09-04T14:01:15Z"
        expired = writer.mark_submission(self.path, operation)
        self.assertFalse(expired["should_call_adapter"])
        return expired["submission"]

    def test_empty_snapshot_preserves_never_dispatched_expiry_tombstone(self):
        expired = self.expire_unsent()
        self.broker_id = None
        snapshot = self.snapshot(include_order=False, at="2026-09-04T14:01:20Z")
        result = reconciliation.apply(self.path, snapshot)
        self.assertEqual(result["outcome"], "reconciled")
        self.assertEqual(store.status(self.path)["reserved_cash_usd"], "0")
        self.assertEqual(writer.status(self.path)["submissions"], [expired])

    def test_external_order_for_never_dispatched_expiry_is_a_durable_incident(self):
        expired = self.expire_unsent()
        self.broker_id = "unexpected-broker-order"
        result = reconciliation.apply(self.path, self.snapshot(at="2026-09-04T14:01:20Z"))
        self.assertEqual(result["outcome"], "unresolved")
        self.assertIn("external_activity_unknown", result["unresolved_reasons"])
        self.assertEqual(writer.status(self.path)["submissions"], [expired])
        self.assertEqual(store.status(self.path)["version"], 2)

    def test_reconciled_rejection_releases_capacity_for_a_later_distinct_attempt(self):
        self.submitted("rejected")
        self.broker_id = None
        rejected_snapshot = self.snapshot(state="rejected")
        reconciled = reconciliation.apply(self.path, rejected_snapshot)
        self.assertEqual(reconciled["outcome"], "reconciled")
        self.assertEqual(store.status(self.path)["reserved_cash_usd"], "0")

        second = deepcopy(self.proposal())
        second.update(intent_id="intent-two", candidate_id="candidate-two",
                      client_order_id="order-two", expected_account_version=2,
                      decision_at="2026-09-04T14:00:51Z",
                      expires_at="2026-09-04T14:01:20Z",
                      quote_at="2026-09-04T14:00:45Z", fx_at="2026-09-04T14:00:45Z")
        admitted = store.admit(self.path, second)
        self.assertEqual((admitted["outcome"], admitted["account"]["attempts"]),
                         ("reserved", 2))
        writer.claim(self.path, self.claim("two", epoch=1, at="2026-09-04T14:00:55Z"))
        operation = {"schema": "order-submission-operation-v1", "operation_id": "submit-two",
                     "intent_id": "intent-two", "owner_id": "writer-a", "epoch": 2,
                     "at": "2026-09-04T14:00:56Z", "expected_account_version": 3}
        result = writer.dispatch_synthetic(self.path, operation, "acknowledged")
        second_snapshot = self.snapshot("second", version=1, at="2026-09-04T14:01:00Z")
        second_snapshot["orders"][0].update(
            client_order_id="order-two", broker_order_id=result["submission"]["broker_order_id"])
        applied = reconciliation.apply(self.path, second_snapshot)
        self.assertEqual((applied["outcome"], applied["order_projection"]["intent_id"]),
                         ("reconciled", "intent-two"))

    def test_empty_order_snapshot_never_resolves_a_lost_acknowledgement(self):
        self.submitted("accept_then_timeout")
        self.broker_id = "synthetic-late-order"
        result = reconciliation.apply(self.path, self.snapshot(include_order=False))
        self.assertEqual(result["outcome"], "unresolved")
        self.assertIn("order_outcome_unknown", result["unresolved_reasons"])
        self.assertEqual(store.status(self.path)["reserved_cash_usd"], "200.80")
        with self.assertRaisesRegex(ValueError, "Reconciliation"):
            writer.claim(self.path, self.claim("next", epoch=1, at="2026-09-04T14:00:55Z"))

        execution = self.execution("execution-late", 2, "100", "2026-09-04T14:00:56Z")
        fee = self.fee("commission-late", "execution-late", "0.35", "2026-09-04T14:00:57Z")
        late = self.snapshot("late", version=1, at="2026-09-04T14:01:00Z", state="filled",
                             executions=[execution], commissions=[fee], cash="299.65", position=2)
        resolved = reconciliation.apply(self.path, late)
        self.assertEqual((resolved["outcome"], resolved["unresolved_reasons"]),
                         ("reconciled", []))

    def test_cumulative_partial_then_fill_updates_cash_position_fee_and_reservation_once(self):
        result = self.submitted("accept_then_timeout")
        self.broker_id = "synthetic-late-order"
        first_execution = self.execution("execution-1", 1, "100", "2026-09-04T14:00:45Z")
        first_fee = self.fee("commission-1", "execution-1", "0.35", "2026-09-04T14:00:46Z")
        partial = self.snapshot(executions=[first_execution, deepcopy(first_execution)],
                                commissions=[first_fee, deepcopy(first_fee)],
                                cash="399.65", position=1)
        partial["orders"][0]["cumulative_executed_quantity"] = 1
        applied = reconciliation.apply(self.path, partial)
        self.assertEqual(applied["order_projection"]["executed_quantity"], 1)
        self.assertEqual((applied["execution_ids"], applied["commission_ids"]),
                         (["execution-1"], ["commission-1"]))
        self.assertEqual(writer.status(self.path)["submissions"][0]["state"], "partially_filled")
        account = store.status(self.path)
        self.assertEqual((account["settled_cash_usd"], account["position_quantity"],
                          account["reserved_cash_usd"]), ("399.65", 1, "100.40"))
        self.assertTrue(reconciliation.apply(self.path, deepcopy(partial))["duplicate"])
        self.assertEqual(store.status(self.path)["version"], 2)

        second_execution = self.execution("execution-2", 1, "99", "2026-09-04T14:00:55Z")
        filled = self.snapshot("two", version=1, at="2026-09-04T14:01:00Z", state="filled",
                               executions=[first_execution, second_execution],
                               commissions=[first_fee], cash="300.65", position=2)
        final = reconciliation.apply(self.path, filled)
        self.assertEqual(final["outcome"], "reconciled")
        self.assertEqual(writer.status(self.path)["submissions"][0]["state"], "filled")
        account = store.status(self.path)
        self.assertEqual((account["settled_cash_usd"], account["position_quantity"],
                          account["reserved_cash_usd"], account["attempts"]),
                         ("300.65", 2, "0.35", 1))

    def test_changed_cumulative_execution_and_cash_position_mismatches_block_without_account_change(self):
        result = self.submitted()
        self.broker_id = result["submission"]["broker_order_id"]
        execution = self.execution("execution-1", 1, "100", "2026-09-04T14:00:45Z")
        bad = self.snapshot(executions=[execution], cash="401", position=0)
        report = reconciliation.apply(self.path, bad)
        self.assertEqual(report["outcome"], "unresolved")
        self.assertIn("currency_cash_mismatch", report["unresolved_reasons"])
        self.assertIn("position_quantity_mismatch", report["unresolved_reasons"])
        account = store.status(self.path)
        self.assertEqual((account["settled_cash_usd"], account["position_quantity"], account["version"]),
                         ("500", 0, 1))
        self.assertIn("position_quantity_mismatch", account["blocked_reasons"])
        second = deepcopy(self.proposal())
        second.update(intent_id="intent-two", candidate_id="candidate-two",
                      client_order_id="order-two", expected_account_version=1,
                      decision_at="2026-09-04T14:00:51Z",
                      expires_at="2026-09-04T14:01:20Z",
                      quote_at="2026-09-04T14:00:30Z", fx_at="2026-09-04T14:00:30Z")
        rejected = store.admit(self.path, second)
        self.assertEqual(rejected["outcome"], "rejected")
        self.assertIn("position_quantity_mismatch", rejected["reasons"])

    def test_snapshot_identity_conflict_is_durable_and_disarming(self):
        result = self.submitted()
        self.broker_id = result["submission"]["broker_order_id"]
        snapshot = self.snapshot()
        reconciliation.apply(self.path, snapshot)
        changed = deepcopy(snapshot)
        changed["currency_cash"]["USD"] = "499"
        incident = reconciliation.apply(self.path, changed)
        self.assertIn("snapshot_identity_conflict", incident["unresolved_reasons"])
        self.assertTrue(reconciliation.apply(self.path, deepcopy(changed))["duplicate"])
        self.assertEqual(len(reconciliation.history(self.path)), 2)
        self.assertEqual(reconciliation.status(self.path)["status"], "unresolved")
        self.assertIn("snapshot_identity_conflict", writer.status(self.path)["unresolved_reasons"])

    def test_terminal_order_regression_is_a_durable_incident(self):
        result = self.submitted()
        self.broker_id = result["submission"]["broker_order_id"]
        execution = self.execution("execution-1", 2, "100", "2026-09-04T14:00:45Z")
        fee = self.fee("commission-1", "execution-1", "0.35", "2026-09-04T14:00:46Z")
        filled = self.snapshot(executions=[execution], commissions=[fee], state="filled",
                               cash="299.65", position=2)
        reconciliation.apply(self.path, filled)
        regressed = self.snapshot("regressed", version=1, at="2026-09-04T14:01:00Z",
                                  executions=[execution], commissions=[fee], state="working",
                                  cash="299.65", position=2)
        report = reconciliation.apply(self.path, regressed)
        self.assertIn("order_state_regression", report["unresolved_reasons"])
        self.assertEqual(store.status(self.path)["version"], 2)

    def test_late_commission_revision_adjusts_once_and_loss_halts_latch(self):
        result = self.submitted()
        self.broker_id = result["submission"]["broker_order_id"]
        execution = self.execution("execution-1", 2, "100", "2026-09-04T14:00:45Z")
        fee = self.fee("commission-1", "execution-1", "0.35", "2026-09-04T14:00:46Z")
        first = self.snapshot(executions=[execution], commissions=[fee], state="filled",
                              cash="299.65", position=2,
                              mark={"equity": "989", "deposits": "0", "withdrawals": "0"})
        reconciliation.apply(self.path, first)
        self.assertEqual(store.status(self.path)["assessment"]["halt_reasons"], ("daily",))
        revised_fee = self.fee("commission-1", "execution-1", "0.45", "2026-09-04T14:00:55Z")
        revised_fee["revision"] = 1
        second = self.snapshot("fee-revision", version=1, at="2026-09-04T14:01:00Z",
                               state="filled", executions=[execution], commissions=[revised_fee],
                               cash="299.55", position=2)
        reconciliation.apply(self.path, second)
        account = store.status(self.path)
        self.assertEqual(account["settled_cash_usd"], "299.55")
        self.assertEqual(account["assessment"]["halt_reasons"], ("daily",))
        self.assertTrue(reconciliation.apply(self.path, deepcopy(second))["duplicate"])
        self.assertEqual(store.status(self.path)["version"], 3)

    def test_startup_and_disconnect_invalidation_require_complete_reconciliation(self):
        result = self.submitted()
        self.broker_id = result["submission"]["broker_order_id"]
        recovered = writer.recover(self.path, {
            "schema": "order-writer-recovery-v1", "recovery_id": "restart-1",
            "owner_id": "writer-a", "epoch": 1, "at": "2026-09-04T14:00:50Z"})
        self.assertIn("reconciliation_required", recovered["unresolved_reasons"])
        self.assertEqual(reconciliation.status(self.path)["status"], "required")
        with self.assertRaisesRegex(ValueError, "Reconciliation"):
            writer.claim(self.path, self.claim("next", epoch=1, at="2026-09-04T14:00:51Z"))
        snapshot = self.snapshot(version=1, at="2026-09-04T14:00:55Z")
        reconciliation.apply(self.path, snapshot)
        claimed = writer.claim(self.path, self.claim("next", epoch=1, at="2026-09-04T14:00:56Z"))
        self.assertEqual(claimed["epoch"], 2)
        disconnected = reconciliation.invalidate(self.path, {
            "schema": "order-reconciliation-invalidation-v1", "event_id": "disconnect-1",
            "at": "2026-09-04T14:01:00Z", "reason": "disconnect"})
        self.assertEqual(disconnected["status"], "required")

    def test_atomic_failure_rolls_back_inbox_account_writer_and_event(self):
        result = self.submitted()
        self.broker_id = result["submission"]["broker_order_id"]
        with contextlib.closing(sqlite3.connect(self.path)) as connection:
            connection.execute(
                "CREATE TRIGGER fail_adjustment BEFORE INSERT ON reconciliation_adjustments "
                "BEGIN SELECT RAISE(ABORT, 'injected reconciliation failure'); END")
            connection.commit()
        with self.assertRaises(sqlite3.Error):
            reconciliation.apply(self.path, self.snapshot())
        self.assertEqual(reconciliation.status(self.path)["inbox_count"], 0)
        self.assertEqual(reconciliation.history(self.path), [])
        self.assertEqual(store.status(self.path)["version"], 1)
        self.assertEqual(writer.status(self.path)["version"], 3)

    def test_mutated_reconciliation_projection_fails_closed_against_event_replay(self):
        result = self.submitted()
        self.broker_id = result["submission"]["broker_order_id"]
        reconciliation.apply(self.path, self.snapshot())
        with contextlib.closing(sqlite3.connect(self.path)) as connection:
            payload = json.loads(connection.execute(
                "SELECT payload FROM reconciliation_state WHERE id=1").fetchone()[0])
            payload["status"] = "required"
            connection.execute("UPDATE reconciliation_state SET payload=? WHERE id=1",
                               (json.dumps(payload),))
            connection.commit()
        with self.assertRaisesRegex(ValueError, "event history|status disagrees"):
            reconciliation.status(self.path)

    def test_cli_and_examples_expose_reconciliation_without_live_mode(self):
        result = self.submitted()
        self.broker_id = result["submission"]["broker_order_id"]
        snapshot_path = Path(self.root.name) / "snapshot.json"
        snapshot_path.write_text(json.dumps(self.snapshot()))
        output = io.StringIO()
        with contextlib.redirect_stdout(output):
            self.assertEqual(main(["order-reconcile", str(self.path), str(snapshot_path)]), 0)
        self.assertFalse(json.loads(output.getvalue())["live_trading_enabled"])
        with contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(main(["order-reconciliation-status", str(self.path)]), 0)
        shipped = json.loads(Path("examples/order-reconciliation.json").read_text())
        self.assertEqual(shipped["schema"], "synthetic-reconciliation-snapshot-v1")

    def test_version_two_writer_store_requires_explicit_reconciliation_migration(self):
        with contextlib.closing(sqlite3.connect(self.path)) as connection:
            for table in ("reconciliation_events", "reconciliation_inbox",
                          "reconciliation_state", "reconciliation_adjustments"):
                connection.execute(f"DROP TABLE {table}")
            connection.execute("PRAGMA user_version=2")
            connection.commit()
        self.assertEqual(writer.status(self.path)["version"], 0)
        with self.assertRaisesRegex(ValueError, "explicit P4.4"):
            reconciliation.status(self.path)


if __name__ == "__main__":
    unittest.main()
