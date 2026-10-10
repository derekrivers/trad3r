from copy import deepcopy
import contextlib
from decimal import Decimal as D
import io
import json
from pathlib import Path
import sqlite3
import tempfile
import unittest

from trad3r import order_allocations as allocations
from trad3r import order_reconciliation as entry_reconciliation
from trad3r import order_sell_reconciliation as sells
from trad3r import order_store as store
from trad3r import order_writer as writer
from trad3r.risk import money
from trad3r.settlement import (CASH_RELEASE_POLICY, SETTLEMENT_CALENDAR_ID,
                               cash_available_at, settlement_date)
from trad3r.__main__ import main


class SellReconciliationTests(unittest.TestCase):
    instrument = "synthetic:NASDAQ:AAPL:USD"

    def setUp(self):
        self.root = tempfile.TemporaryDirectory()
        self.addCleanup(self.root.cleanup)
        self.path = Path(self.root.name) / "orders.sqlite"
        self.prepare()

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

    def prepare(self, allocation_quantity=2, fee_bound="0.35"):
        allocations.initialize(self.path, self.account())
        store.admit(self.path, self.entry())
        writer.claim(self.path, {
            "schema": "order-writer-claim-v1", "claim_id": "entry-claim",
            "owner_id": "entry-writer", "at": "2026-09-04T14:00:15Z", "expected_epoch": 0,
        })
        submitted = writer.dispatch_synthetic(self.path, {
            "schema": "order-submission-operation-v1", "operation_id": "entry-submit",
            "intent_id": "entry-intent", "owner_id": "entry-writer", "epoch": 1,
            "at": "2026-09-04T14:00:20Z", "expected_account_version": 1,
        }, "acknowledged")
        self.entry_order_id = submitted["submission"]["broker_order_id"]
        entry_reconciliation.apply(self.path, {
            "schema": "synthetic-reconciliation-snapshot-v1", "snapshot_id": "entry-snapshot",
            "reconciliation_id": "entry-reconciliation", "account_id": "synthetic-test",
            "environment": "synthetic", "at": "2026-09-04T14:00:40Z",
            "expected_reconciliation_version": 0,
            "completeness": {key: True for key in (
                "orders", "executions", "positions", "currency_cash", "commissions", "settlement")},
            "orders": [{"client_order_id": "entry-order", "broker_order_id": self.entry_order_id,
                        "state": "filled", "original_quantity": 2,
                        "cumulative_executed_quantity": 2}],
            "executions": [{"execution_id": "entry-fill", "client_order_id": "entry-order",
                            "broker_order_id": self.entry_order_id, "instrument_id": self.instrument,
                            "symbol": "AAPL", "currency": "USD", "side": "buy", "quantity": 2,
                            "price_usd": "100", "at": "2026-09-04T14:00:30Z"}],
            "commissions": [{"commission_id": "entry-fee", "execution_id": "entry-fill",
                             "currency": "USD", "amount_usd": "0.35",
                             "at": "2026-09-04T14:00:31Z", "revision": 0}],
            "currency_cash": {"USD": "299.65"},
            "positions": [{"instrument_id": self.instrument, "symbol": "AAPL",
                           "currency": "USD", "quantity": 2}],
            "unsettled_usd": "0", "pending_settlements": [],
            "mark": {"equity": "1000", "deposits": "0", "withdrawals": "0"},
        })
        writer.claim(self.path, {
            "schema": "order-writer-claim-v1", "claim_id": "management-claim",
            "owner_id": "management-writer", "at": "2026-09-04T14:00:45Z",
            "expected_epoch": 1,
        })
        self.allocate_exit("allocation-exit", "exit-order", allocation_quantity,
                           fee_bound, "2026-09-04T14:00:50Z")

    def allocate_exit(self, allocation_id, client_order_id, quantity, fee_bound, decision_at):
        account, reconciled, managed, allocation = (
            store.status(self.path), entry_reconciliation.status(self.path),
            writer.status(self.path), allocations.status(self.path))
        request = {
            "schema": "reducing-allocation-request-v1", "allocation_id": allocation_id,
            "client_order_id": client_order_id, "account_id": "synthetic-test",
            "environment": "synthetic", "entry_intent_id": "entry-intent",
            "instrument_id": self.instrument, "purpose": "reducing_exit", "quantity": quantity,
            "fee_bound_usd": fee_bound, "decision_at": decision_at,
            "expires_at": "2026-09-04T14:01:35Z", "quote_at": "2026-09-04T14:00:45Z",
            "fx_at": "2026-09-04T14:00:45Z", "owner_id": "management-writer",
            "writer_epoch": managed["epoch"], "expected_account_version": account["version"],
            "expected_reconciliation_version": reconciled["version"],
            "expected_writer_version": managed["version"],
            "expected_allocation_version": allocation["version"],
            "expected_policy_sha256": account["policy_sha256"],
        }
        self.assertEqual(allocations.admit(self.path, request)["outcome"], "reserved")

    def buy_order(self):
        return {"client_order_id": "entry-order", "order_id": self.entry_order_id,
                "side": "buy", "state": "filled", "original_quantity": 2,
                "cumulative_executed_quantity": 2}

    def buy_execution(self):
        return {"execution_id": "entry-fill", "client_order_id": "entry-order",
                "order_id": self.entry_order_id, "instrument_id": self.instrument,
                "symbol": "AAPL", "currency": "USD", "side": "buy", "quantity": 2,
                "price_usd": "100", "at": "2026-09-04T14:00:30Z"}

    def buy_fee(self):
        return {"commission_id": "entry-fee", "execution_id": "entry-fill",
                "currency": "USD", "amount_usd": "0.35", "at": "2026-09-04T14:00:31Z",
                "revision": 0, "final": True}

    def sell_execution(self, identity="sell-fill", quantity=2, price="99.5",
                       at="2026-09-04T14:00:55Z", client="exit-order"):
        return {"execution_id": identity, "client_order_id": client,
                "order_id": "synthetic-exit", "instrument_id": self.instrument,
                "symbol": "AAPL", "currency": "USD", "side": "sell", "quantity": quantity,
                "price_usd": price, "at": at}

    def sell_fee(self, identity="exit-fee", execution="sell-fill", amount="0.35",
                 revision=0, final=True, at="2026-09-04T14:00:56Z"):
        return {"commission_id": identity, "execution_id": execution, "currency": "USD",
                "amount_usd": amount, "at": at, "revision": revision, "final": final}

    def lot(self, execution, fee="0.35", status="final"):
        gross = money(execution["price_usd"]) * execution["quantity"]
        due = settlement_date("2026-09-04")
        return {"execution_id": execution["execution_id"], "gross_usd": str(gross),
                "fee_usd": fee, "fee_status": status, "net_usd": str(gross - money(fee)),
                "settles_on": due.isoformat(), "available_at": cash_available_at(due).isoformat(),
                "settlement_calendar_id": SETTLEMENT_CALENDAR_ID,
                "cash_release_policy": CASH_RELEASE_POLICY}

    def snapshot(self, identity="one", sell_executions=None, sell_fees=None,
                 sell_state="filled", position=0, pending=None, at="2026-09-04T14:01:00Z",
                 complete=True, mark=None):
        sell_executions = sell_executions or []
        sell_fees = sell_fees or []
        pending = pending or []
        account, managed, allocation, reconciled = (
            store.status(self.path), writer.status(self.path), allocations.status(self.path),
            sells.status(self.path))
        orders = [self.buy_order(), {
            "client_order_id": "exit-order", "order_id": "synthetic-exit", "side": "sell",
            "state": sell_state, "original_quantity": 2,
            "cumulative_executed_quantity": sum(row["quantity"] for row in sell_executions),
        }]
        return {
            "schema": "synthetic-reducing-reconciliation-v1",
            "snapshot_id": "sell-snapshot-" + identity,
            "reconciliation_id": "sell-reconciliation-" + identity,
            "account_id": "synthetic-test", "environment": "synthetic", "at": at,
            "expected_reducing_reconciliation_version": reconciled["version"],
            "expected_account_version": account["version"],
            "expected_writer_version": managed["version"],
            "expected_allocation_version": allocation["version"],
            "completeness": {key: complete for key in (
                "orders", "executions", "positions", "currency_cash", "commissions", "settlement")},
            "orders": orders, "executions": [self.buy_execution(), *sell_executions],
            "commissions": [self.buy_fee(), *sell_fees], "currency_cash": {"USD": "299.65"},
            "positions": ([] if position == 0 else [{"instrument_id": self.instrument,
                           "symbol": "AAPL", "currency": "USD", "quantity": position}]),
            "unsettled_usd": str(sum((money(row["net_usd"]) for row in pending), D("0"))),
            "pending_settlements": pending,
            "mark": mark or {"equity": "1000", "deposits": "0", "withdrawals": "0"},
        }

    def test_partial_then_full_sell_moves_holdings_and_commitment_without_crediting_cash(self):
        first_execution = self.sell_execution(quantity=1)
        first_lot = self.lot(first_execution, fee="0.15")
        first = sells.apply(self.path, self.snapshot(
            "partial", [first_execution], [self.sell_fee(amount="0.15")],
            sell_state="working", position=1, pending=[first_lot]))
        self.assertEqual((first["verified_quantity"], first["committed_sell_quantity"],
                          first["available_sell_quantity"]), (1, 1, 0))
        account = store.status(self.path)
        self.assertEqual((account["settled_cash_usd"], account["reserved_cash_usd"]),
                         ("299.65", "0.20"))

        second_execution = self.sell_execution("sell-fill-two", quantity=1,
                                               at="2026-09-04T14:01:02Z")
        second_fee = self.sell_fee("exit-fee-two", "sell-fill-two", "0.20",
                                   at="2026-09-04T14:01:03Z")
        second_lot = self.lot(second_execution, fee="0.20")
        final = sells.apply(self.path, self.snapshot(
            "filled", [first_execution, second_execution],
            [self.sell_fee(amount="0.15"), second_fee], position=0,
            pending=[first_lot, second_lot], at="2026-09-04T14:01:05Z"))
        self.assertEqual((final["verified_quantity"], final["committed_sell_quantity"]), (0, 0))
        account = store.status(self.path)
        self.assertEqual(account["settled_cash_usd"], "299.65")
        self.assertEqual(tuple(money(account[key]) for key in (
            "reserved_cash_usd", "reserved_exposure_gbp", "reserved_loss_gbp")),
            (D("0"), D("0"), D("0")))
        self.assertEqual(account["unsettled_usd"], "198.65")
        self.assertEqual(account["attempts"], 1)
        self.assertIn("reducing_episode_transition_required", account["blocked_reasons"])
        self.assertFalse(final["settlement_release_enabled"])

    def test_two_sell_orders_conserve_quantity_fees_and_pending_proceeds(self):
        path = Path(self.root.name) / "two-orders.sqlite"
        original_path = self.path
        self.path = path
        try:
            self.prepare(allocation_quantity=1, fee_bound="0.15")
            self.allocate_exit("allocation-exit-two", "exit-order-two", 1, "0.20",
                               "2026-09-04T14:00:52Z")
            first = self.sell_execution("sell-fill-one", quantity=1)
            second = self.sell_execution(
                "sell-fill-two", quantity=1, price="100", at="2026-09-04T14:00:57Z",
                client="exit-order-two")
            second["order_id"] = "synthetic-exit-two"
            first_fee = self.sell_fee("exit-fee-one", "sell-fill-one", "0.15")
            second_fee = self.sell_fee(
                "exit-fee-two", "sell-fill-two", "0.20", at="2026-09-04T14:00:58Z")
            lots = [self.lot(first, fee="0.15"), self.lot(second, fee="0.20")]
            snapshot = self.snapshot(
                "two-orders", [first, second], [first_fee, second_fee],
                pending=list(reversed(lots)))
            snapshot["orders"][1].update(
                original_quantity=1, cumulative_executed_quantity=1)
            snapshot["orders"].append({
                "client_order_id": "exit-order-two", "order_id": "synthetic-exit-two",
                "side": "sell", "state": "filled", "original_quantity": 1,
                "cumulative_executed_quantity": 1,
            })
            result = sells.apply(path, snapshot)
            self.assertEqual((result["verified_quantity"], result["committed_sell_quantity"]),
                             (0, 0))
            self.assertEqual(result["incurred_exit_fees_usd"], "0.35")
            account = store.status(path)
            self.assertEqual(account["settled_cash_usd"], "299.65")
            self.assertEqual(account["unsettled_usd"], "199.15")
            self.assertEqual(len(account["pending_settlements"]), 2)
        finally:
            self.path = original_path

    def test_missing_provisional_and_revised_final_fee_update_one_pending_lot(self):
        execution = self.sell_execution()
        missing_lot = self.lot(execution, status="missing")
        missing = sells.apply(self.path, self.snapshot(
            "missing", [execution], [], pending=[missing_lot],
            mark={"equity": "699", "deposits": "0", "withdrawals": "0"}))
        self.assertEqual(missing["unresolved_reasons"], ["fee_incomplete"])
        self.assertEqual(store.status(self.path)["reserved_cash_usd"], "0.35")
        self.assertEqual(store.status(self.path)["assessment"]["halt_reasons"],
                         ("daily", "overall", "weekly"))

        provisional_fee = self.sell_fee(amount="0.30", final=False,
                                        at="2026-09-04T14:01:01Z")
        provisional_lot = self.lot(execution, fee="0.30", status="provisional")
        provisional = sells.apply(self.path, self.snapshot(
            "provisional", [execution], [provisional_fee], pending=[provisional_lot],
            at="2026-09-04T14:01:05Z"))
        self.assertEqual(provisional["unresolved_reasons"], ["fee_incomplete"])

        final_fee = self.sell_fee(amount="0.35", revision=1, final=True,
                                  at="2026-09-04T14:01:06Z")
        final_lot = self.lot(execution)
        completed = sells.apply(self.path, self.snapshot(
            "final", [execution], [final_fee], pending=[final_lot],
            at="2026-09-04T14:01:10Z"))
        self.assertEqual(completed["unresolved_reasons"], [])
        self.assertEqual(money(store.status(self.path)["reserved_cash_usd"]), D("0"))
        self.assertNotIn("fee_incomplete", writer.status(self.path)["unresolved_reasons"])

        revised_fee = self.sell_fee(amount="0.45", revision=2, final=True,
                                    at="2026-09-04T14:01:11Z")
        revised_lot = self.lot(execution, fee="0.45")
        revised = sells.apply(self.path, self.snapshot(
            "revision", [execution], [revised_fee], pending=[revised_lot],
            at="2026-09-04T14:01:15Z"))
        self.assertEqual(revised["pending_lots"][0]["net_usd"], "198.55")
        account = store.status(self.path)
        self.assertEqual(account["settled_cash_usd"], "299.65")
        self.assertEqual(account["assessment"]["halt_reasons"],
                         ("daily", "overall", "weekly"))

    def test_working_unknown_and_absent_sell_evidence_never_frees_reserved_shares(self):
        for index, state in enumerate(("working", "unknown", None)):
            with self.subTest(state=state):
                path = Path(self.root.name) / f"remainder-{index}.sqlite"
                original = self.path
                self.path = path
                try:
                    self.prepare()
                    snapshot = self.snapshot(f"remainder-{index}", sell_state=state or "working",
                                             position=2)
                    if state is None:
                        snapshot["orders"] = [self.buy_order()]
                    result = sells.apply(path, snapshot)
                    self.assertEqual((result["verified_quantity"],
                                      result["committed_sell_quantity"],
                                      result["available_sell_quantity"]), (2, 2, 0))
                    self.assertEqual(store.status(path)["position_quantity"], 2)
                finally:
                    self.path = original

    def test_exact_duplicate_and_new_envelope_do_not_double_count_execution(self):
        execution = self.sell_execution()
        fee = self.sell_fee()
        lot = self.lot(execution)
        snapshot = self.snapshot("same", [execution], [fee], pending=[lot])
        first = sells.apply(self.path, snapshot)
        reordered = deepcopy(snapshot)
        for field in ("orders", "executions", "commissions", "pending_settlements"):
            reordered[field].reverse()
        duplicate = sells.apply(self.path, reordered)
        self.assertTrue(duplicate["duplicate"])
        self.assertEqual(duplicate["account_version"], first["account_version"])
        again = sells.apply(self.path, self.snapshot(
            "again", [execution], [fee], pending=[lot], at="2026-09-04T14:01:05Z"))
        self.assertEqual(len(again["pending_lots"]), 1)
        self.assertEqual(store.status(self.path)["settled_cash_usd"], "299.65")

    def test_changed_snapshot_identity_latches_even_with_stale_source_time(self):
        execution = self.sell_execution()
        original = self.snapshot("identity", [execution], [self.sell_fee()],
                                 pending=[self.lot(execution)])
        sells.apply(self.path, original)
        changed = deepcopy(original)
        changed["at"] = "2026-09-04T14:00:59Z"
        changed["mark"] = {"equity": "999", "deposits": "0", "withdrawals": "0"}
        result = sells.apply(self.path, changed)
        self.assertEqual(result["unresolved_reasons"], ["snapshot_identity_conflict"])
        self.assertFalse(writer.status(self.path)["dispatch_allowed"])
        self.assertTrue(sells.apply(self.path, deepcopy(changed))["duplicate"])
        self.assertEqual(len(sells.history(self.path)), 2)
        with store.database(self.path) as connection:
            self.assertEqual(connection.execute(
                "SELECT COUNT(*) FROM reducing_reconciliation_inbox").fetchone()[0], 2)

    def test_changed_execution_manual_sell_and_overfill_are_retained_incidents(self):
        original = self.sell_execution()
        sells.apply(self.path, self.snapshot(
            "original", [original], [self.sell_fee()], pending=[self.lot(original)]))
        changed = self.sell_execution(price="98")
        changed_result = sells.apply(self.path, self.snapshot(
            "changed", [changed], [self.sell_fee()], pending=[self.lot(changed)],
            at="2026-09-04T14:01:05Z"))
        self.assertEqual(changed_result["outcome"], "unresolved")
        self.assertIn("execution_history_changed", changed_result["unresolved_reasons"])
        clean = sells.apply(self.path, self.snapshot(
            "clean-after-conflict", [original], [self.sell_fee()], pending=[self.lot(original)],
            at="2026-09-04T14:01:10Z"))
        self.assertIn("execution_history_changed", clean["unresolved_reasons"])
        self.assertEqual(store.status(self.path)["position_quantity"], 0)

        cases = []
        manual = self.sell_execution(client="manual-order")
        cases.append(self.snapshot("manual", [manual], [self.sell_fee()],
                                   pending=[self.lot(manual)]))
        overfill = self.sell_execution(quantity=3)
        cases.append(self.snapshot("overfill", [overfill], [self.sell_fee()], position=0,
                                   pending=[self.lot(overfill)]))
        cases.append(self.snapshot("wrong-side", [original], [self.sell_fee()],
                                   pending=[self.lot(original)]))
        for index, snapshot in enumerate(cases):
            with self.subTest(index=index):
                path = Path(self.root.name) / f"incident-{index}.sqlite"
                original = self.path
                self.path = path
                try:
                    self.prepare()
                    snapshot = self.snapshot(
                        f"incident-{index}", snapshot["executions"][1:],
                        snapshot["commissions"][1:], position=0,
                        pending=snapshot["pending_settlements"])
                    if index == 2:
                        snapshot["orders"][1]["side"] = "buy"
                    before = store.status(path)
                    result = sells.apply(path, snapshot)
                    self.assertEqual(result["outcome"], "unresolved")
                    if index == 2:
                        self.assertIn("order_side_mismatch", result["unresolved_reasons"])
                    after = store.status(path)
                    self.assertEqual((after["version"], after["position_quantity"],
                                      after["settled_cash_usd"]),
                                     (before["version"], before["position_quantity"],
                                      before["settled_cash_usd"]))
                    with store.database(path) as connection:
                        self.assertEqual(connection.execute(
                            "SELECT COUNT(*) FROM reducing_reconciliation_inbox").fetchone()[0], 1)
                finally:
                    self.path = original

    def test_pending_mismatch_and_incomplete_snapshot_change_no_account_fact(self):
        execution = self.sell_execution()
        fee = self.sell_fee()
        lot = self.lot(execution)
        incomplete = self.snapshot(
            "incomplete", [execution], [fee], pending=[lot], complete=False)
        incomplete.update(
            orders=[self.buy_order()], executions=[self.buy_execution()],
            commissions=[self.buy_fee()], positions=[], unsettled_usd="0",
            pending_settlements=[])
        cases = (self.snapshot("pending", [execution], [fee], pending=[]), incomplete)
        for index, snapshot in enumerate(cases):
            with self.subTest(index=index):
                path = Path(self.root.name) / f"transient-{index}.sqlite"
                original = self.path
                self.path = path
                try:
                    self.prepare()
                    snapshot.update(
                        expected_account_version=store.status(path)["version"],
                        expected_writer_version=writer.status(path)["version"],
                        expected_allocation_version=allocations.status(path)["version"],
                        expected_reducing_reconciliation_version=0)
                    before = store.status(path)
                    result = sells.apply(path, snapshot)
                    self.assertEqual(result["outcome"], "unresolved")
                    self.assertEqual(store.status(path)["version"], before["version"])
                    if index == 1:
                        self.assertEqual(result["unresolved_reasons"], ["snapshot_incomplete"])
                        complete = sells.apply(path, self.snapshot(
                            "complete-after-incomplete", sell_state="working", position=2,
                            at="2026-09-04T14:01:05Z"))
                        self.assertEqual(complete["unresolved_reasons"], [])
                        self.assertEqual(store.status(path)["position_quantity"], 2)
                finally:
                    self.path = original

    def test_failure_rolls_back_inbox_account_pending_and_event(self):
        execution = self.sell_execution()
        snapshot = self.snapshot("rollback", [execution], [self.sell_fee()],
                                 pending=[self.lot(execution)])
        before = store.status(self.path)
        with contextlib.closing(sqlite3.connect(self.path)) as connection:
            connection.execute(
                "CREATE TRIGGER fail_sell_event BEFORE INSERT ON reducing_reconciliation_events "
                "BEGIN SELECT RAISE(ABORT, 'injected sell event failure'); END")
            connection.commit()
        with self.assertRaises(sqlite3.Error):
            sells.apply(self.path, snapshot)
        self.assertEqual(store.status(self.path), before)
        with store.database(self.path) as connection:
            self.assertEqual(connection.execute(
                "SELECT COUNT(*) FROM reducing_reconciliation_inbox").fetchone()[0], 0)

    def test_replay_rejects_rehashed_entry_history_and_account_projection(self):
        for index, mutation in enumerate(("entry", "account")):
            with self.subTest(mutation=mutation):
                path = Path(self.root.name) / f"corrupt-{index}.sqlite"
                original = self.path
                self.path = path
                try:
                    self.prepare()
                    execution = self.sell_execution()
                    sells.apply(path, self.snapshot(
                        "corrupt", [execution], [self.sell_fee()], pending=[self.lot(execution)]))
                    with contextlib.closing(sqlite3.connect(path)) as connection:
                        if mutation == "entry":
                            receipt = connection.execute(
                                "SELECT receipt_id,payload FROM reducing_reconciliation_inbox"
                            ).fetchone()
                            snapshot = store.decode(receipt[1])
                            snapshot["executions"][0]["price_usd"] = "90"
                            snapshot["currency_cash"]["USD"] = "319.65"
                            changed_sha = store.digest(snapshot)
                            event = store.decode(connection.execute(
                                "SELECT payload FROM reducing_reconciliation_events").fetchone()[0])
                            event["input_sha256"] = changed_sha
                            base = {key: value for key, value in event.items() if key != "event_id"}
                            event["event_id"] = store.digest(base)
                            connection.execute(
                                "UPDATE reducing_reconciliation_inbox SET receipt_id=?,payload_sha256=?,payload=?",
                                (changed_sha, changed_sha, store.pack(snapshot)))
                            connection.execute(
                                "UPDATE reducing_reconciliation_events SET event_id=?,input_sha256=?,payload_sha256=?,payload=?",
                                (event["event_id"], changed_sha, store.digest(event), store.pack(event)))
                        else:
                            row = connection.execute(
                                "SELECT reconciliation_id,payload FROM reconciliation_adjustments "
                                "ORDER BY committed_version DESC LIMIT 1").fetchone()
                            adjustment = store.decode(row[1])
                            adjustment["reserved_cash_usd"] = "1"
                            connection.execute(
                                "UPDATE reconciliation_adjustments SET payload=? WHERE reconciliation_id=?",
                                (store.pack(adjustment), row[0]))
                            connection.execute(
                                "UPDATE audit SET payload_sha256=? WHERE event_key=?",
                                (store.digest(adjustment), row[0]))
                            account = store.decode(connection.execute(
                                "SELECT payload FROM account_state").fetchone()[0])
                            account["reserved_cash_usd"] = "1"
                            connection.execute("UPDATE account_state SET payload=?", (store.pack(account),))
                        connection.commit()
                    for read in (sells.status, store.status, writer.status, entry_reconciliation.status):
                        with self.assertRaises(ValueError):
                            read(path)
                finally:
                    self.path = original

    def test_sell_history_blocks_entry_only_reconciliation_and_survives_restart(self):
        execution = self.sell_execution()
        sells.apply(self.path, self.snapshot(
            "restart", [execution], [self.sell_fee()], pending=[self.lot(execution)]))
        self.assertEqual(len(sells.history(self.path)), 1)
        self.assertEqual(sells.status(self.path)["verified_quantity"], 0)
        with store.database(self.path) as connection:
            prior = store.decode(connection.execute(
                "SELECT payload FROM reconciliation_inbox WHERE snapshot_id='entry-snapshot'"
            ).fetchone()[0])
        prior.update(snapshot_id="late-entry-snapshot", reconciliation_id="late-entry-reconciliation",
                     at="2026-09-04T14:01:05Z", expected_reconciliation_version=1)
        with self.assertRaisesRegex(ValueError, "reducing reconciliation"):
            entry_reconciliation.apply(self.path, prior)

    def test_v3_store_has_no_sell_reconciliation_surface(self):
        path = Path(self.root.name) / "v3.sqlite"
        store.initialize(path, self.account())
        with self.assertRaisesRegex(ValueError, "fresh v4"):
            sells.status(path)

    def test_cli_applies_and_reports_without_dispatch_or_release_capability(self):
        execution = self.sell_execution()
        snapshot = self.snapshot("cli", [execution], [self.sell_fee()],
                                 pending=[self.lot(execution)])
        source = Path(self.root.name) / "sell-snapshot.json"
        source.write_text(json.dumps(snapshot))
        with contextlib.redirect_stdout(io.StringIO()) as output:
            self.assertEqual(main(["order-reducing-reconcile", str(self.path), str(source)]), 0)
        self.assertEqual(json.loads(output.getvalue())["outcome"], "reconciled")
        for command, key in (("order-reducing-reconciliation-status", "pending_lots"),
                             ("order-reducing-reconciliation-history", None)):
            with contextlib.redirect_stdout(io.StringIO()) as output:
                self.assertEqual(main([command, str(self.path)]), 0)
            report = json.loads(output.getvalue())
            self.assertTrue(report if key is None else report[key])
        self.assertFalse(sells.status(self.path)["dispatch_authorized"])
        self.assertFalse(sells.status(self.path)["settlement_release_enabled"])


if __name__ == "__main__":
    unittest.main()
