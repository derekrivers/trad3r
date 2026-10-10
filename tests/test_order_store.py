from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy
import contextlib
import io
import json
from pathlib import Path
import sqlite3
import subprocess
import sys
import tempfile
import unittest

from trad3r import order_store as store
from trad3r.__main__ import main


class OrderStoreTests(unittest.TestCase):
    def setUp(self):
        self.root = tempfile.TemporaryDirectory()
        self.addCleanup(self.root.cleanup)
        self.path = Path(self.root.name) / "orders.sqlite"
        store.initialize(self.path, self.snapshot())

    def snapshot(self, **changes):
        value = {
            "schema": "synthetic-order-account-v1",
            "account_id": "synthetic-test", "environment": "synthetic",
            "at": "2026-09-04T14:00:00Z", "settled_cash_usd": "500",
            "position_quantity": 0,
            "mark": {"equity": "1000", "deposits": "0", "withdrawals": "0"},
            "session_start": {"equity": "1000", "deposits": "0", "withdrawals": "0"},
            "week_start": {"equity": "1000", "deposits": "0", "withdrawals": "0"},
            "ledger_version": 4, "risk_version": 7, "evidence_version": 2,
            "halt_reasons": [],
        }
        value.update(changes)
        return value

    def proposal(self, identity="one", version=0, **changes):
        value = {
            "schema": "order-admission-v1", "account_id": "synthetic-test",
            "environment": "synthetic", "intent_id": f"intent-{identity}",
            "candidate_id": f"candidate-{identity}", "client_order_id": f"order-{identity}",
            "decision_at": "2026-09-04T14:00:30Z", "expires_at": "2026-09-04T14:01:15Z",
            "expected_account_version": version, "expected_ledger_version": 4,
            "expected_risk_version": 7, "expected_evidence_version": 2,
            "expected_policy_sha256": store.digest(store._policy_payload()),
            "instrument_id": "synthetic:NASDAQ:AAPL:USD", "symbol": "AAPL",
            "currency": "USD", "side": "buy", "purpose": "entry", "quantity": 1,
            "order_type": "limit", "time_in_force": "day", "limit_price_usd": "100",
            "stop_price_usd": "98", "entry_fee_usd": "0.35", "exit_fee_usd": "0.35",
            "slippage_usd_per_share": "0.05", "usd_to_gbp": "0.8",
            "quote_at": "2026-09-04T14:00:15Z", "fx_at": "2026-09-04T14:00:15Z",
        }
        value.update(changes)
        return value

    def fresh(self, name, **snapshot_changes):
        path = Path(self.root.name) / f"{name}.sqlite"
        store.initialize(path, self.snapshot(**snapshot_changes))
        return path

    def test_atomic_reservation_survives_restart_with_exact_allocations(self):
        result = store.admit(self.path, self.proposal())
        self.assertEqual(result["outcome"], "reserved")
        self.assertEqual(result["reservation"], {
            "cash_usd": "100.75", "exposure_gbp": "80.040",
            "planned_loss_gbp": "2.240", "expires_at": "2026-09-04T14:01:15+00:00",
        })
        self.assertEqual(result["account"]["attempts"], 1)
        self.assertEqual(result["account"]["available_settled_cash_usd"], "399.25")
        self.assertEqual(result["account"]["blocked_reasons"], ["entry_slot_unavailable"])
        reopened = json.loads(subprocess.check_output(
            [sys.executable, "-m", "trad3r", "order-status", str(self.path)], text=True
        ))
        self.assertEqual(reopened["reserved_cash_usd"], "100.75")
        self.assertEqual(reopened["reserved_loss_gbp"], "2.240")
        self.assertFalse(reopened["live_trading_enabled"])
        self.assertEqual(len(store.history(self.path)), 1)

    def test_exact_retry_precedes_stale_version_and_changed_identity_blocks(self):
        proposal = self.proposal()
        first = store.admit(self.path, proposal)
        duplicate = store.admit(self.path, deepcopy(proposal))
        self.assertTrue(duplicate["duplicate"])
        self.assertEqual(duplicate["committed_version"], first["committed_version"])
        self.assertEqual(duplicate["account"]["attempts"], 1)
        changed = deepcopy(proposal)
        changed["quantity"] = 2
        conflict = store.admit(self.path, changed)
        self.assertEqual(conflict["outcome"], "identity_conflict")
        self.assertIn("identity_conflict", conflict["account"]["blocked_reasons"])
        self.assertIn("entry_slot_unavailable", conflict["account"]["blocked_reasons"])
        repeat = store.admit(self.path, changed)
        self.assertTrue(repeat["duplicate"])
        self.assertEqual(repeat["account"]["version"], 2)
        self.assertEqual(len(store.history(self.path)), 2)

    def test_candidate_or_client_identity_cannot_be_reused(self):
        store.admit(self.path, self.proposal())
        for field in ("candidate_id", "client_order_id"):
            path = self.fresh(field)
            first = self.proposal()
            store.admit(path, first)
            changed = self.proposal("two", version=1, **{field: first[field]})
            result = store.admit(path, changed)
            self.assertEqual(result["outcome"], "identity_conflict")
            self.assertTrue(result["account"]["blocked"])

    def test_concurrent_admissions_cannot_share_slot_cash_or_version(self):
        def attempt(identity):
            try:
                return store.admit(self.path, self.proposal(identity))["outcome"]
            except ValueError as error:
                self.assertIn("version changed", str(error))
                return "stale"
        with ThreadPoolExecutor(max_workers=2) as pool:
            results = list(pool.map(attempt, ("one", "two")))
        self.assertCountEqual(results, ["reserved", "stale"])
        report = store.status(self.path)
        self.assertEqual(report["version"], 1)
        self.assertEqual(report["attempts"], 1)
        self.assertEqual(report["reserved_cash_usd"], "100.75")
        self.assertEqual(len(store.history(self.path)), 1)

    def test_second_current_admission_is_rejected_without_overreservation(self):
        store.admit(self.path, self.proposal())
        second = store.admit(self.path, self.proposal("two", version=1))
        self.assertEqual(second["outcome"], "rejected")
        self.assertEqual(second["reasons"], ["entry_slot_unavailable"])
        self.assertTrue(second["attempt_consumed"])
        report = store.status(self.path)
        self.assertEqual(report["attempts"], 2)
        self.assertEqual(report["reserved_cash_usd"], "100.75")
        self.assertEqual(report["reserved_loss_gbp"], "2.240")

    def test_three_evaluated_rejections_consume_slots_but_fourth_does_not(self):
        for index in range(3):
            result = store.admit(self.path, self.proposal(
                str(index), version=index, stop_price_usd="90"
            ))
            self.assertEqual(result["outcome"], "rejected")
            self.assertTrue(result["attempt_consumed"])
            self.assertIn("trade_loss_limit", result["reasons"])
        fourth = store.admit(self.path, self.proposal("four", version=3, stop_price_usd="90"))
        self.assertEqual(fourth["outcome"], "rejected")
        self.assertFalse(fourth["attempt_consumed"])
        self.assertIn("entry_attempt_limit", fourth["reasons"])
        self.assertEqual(store.status(self.path)["attempts"], 3)
        self.assertEqual(len(store.history(self.path)), 4)

    def test_malformed_or_stale_proposals_do_not_consume_attempt_or_write(self):
        cases = []
        missing = self.proposal()
        del missing["stop_price_usd"]
        cases.append(missing)
        cases.append(self.proposal(expires_at="2026-09-04T14:00:30Z"))
        cases.append(self.proposal(expected_ledger_version=5))
        cases.append(self.proposal(expected_policy_sha256="0" * 64))
        cases.append(self.proposal(version=1))
        cases.append(self.proposal(limit_price_usd=100))
        cases.append(self.proposal(limit_price_usd="1e2"))
        cases.append(self.proposal(decision_at=0))
        for proposal in cases:
            with self.assertRaises(ValueError):
                store.admit(self.path, proposal)
            self.assertEqual(store.status(self.path)["attempts"], 0)
            self.assertEqual(store.history(self.path), [])

    def test_stale_evidence_is_rejected_and_authority_is_bound_to_expiry(self):
        expired = store.admit(self.path, self.proposal(
            decision_at="2026-09-04T14:01:16Z", expires_at="2026-09-04T14:01:30Z"
        ))
        self.assertEqual(expired["outcome"], "rejected")
        self.assertIn("account_stale_or_future", expired["reasons"])
        self.assertIn("quote_stale_or_future", expired["reasons"])
        self.assertIsNone(expired["reservation"])
        self.assertEqual(store.status(self.path)["reserved_cash_usd"], "0")

    def test_cash_exposure_trade_and_loss_headroom_each_fail_closed(self):
        cases = (
            ("cash", {"settled_cash_usd": "50"}, {}, "insufficient_settled_cash"),
            ("exposure", {}, {"quantity": 7, "stop_price_usd": "99.90",
                              "entry_fee_usd": "0", "exit_fee_usd": "0"}, "exposure_limit"),
            ("trade", {}, {"stop_price_usd": "90"}, "trade_loss_limit"),
            ("daily", {"mark": {"equity": "992", "deposits": "0", "withdrawals": "0"}},
             {}, "daily_loss_headroom"),
        )
        for name, snapshot_changes, proposal_changes, reason in cases:
            path = self.fresh(name, **snapshot_changes)
            result = store.admit(path, self.proposal(**proposal_changes))
            self.assertEqual(result["outcome"], "rejected")
            self.assertIn(reason, result["reasons"])
            self.assertEqual(result["account"]["reserved_cash_usd"], "0")

    def test_triggered_halt_is_preserved_and_consumes_an_evaluated_attempt(self):
        path = self.fresh(
            "halted", mark={"equity": "700", "deposits": "0", "withdrawals": "0"},
            halt_reasons=["daily", "overall", "weekly"]
        )
        result = store.admit(path, self.proposal())
        self.assertEqual(result["outcome"], "rejected")
        self.assertTrue(result["attempt_consumed"])
        self.assertEqual(result["account"]["blocked_reasons"], ["daily", "overall", "weekly"])

    def test_failed_audit_write_rolls_back_intent_attempt_and_reservations(self):
        with sqlite3.connect(self.path) as connection:
            connection.execute(
                "CREATE TRIGGER fail_audit BEFORE INSERT ON audit "
                "BEGIN SELECT RAISE(ABORT, 'injected write failure'); END"
            )
        with self.assertRaises(sqlite3.Error):
            store.admit(self.path, self.proposal())
        report = store.status(self.path)
        self.assertEqual((report["version"], report["attempts"], report["reserved_cash_usd"]), (0, 0, "0"))
        self.assertEqual(store.history(self.path), [])

    def test_missing_corrupt_or_mutated_store_fails_without_reinitialising(self):
        missing = Path(self.root.name) / "missing.sqlite"
        with self.assertRaises(sqlite3.Error):
            store.status(missing)
        self.assertFalse(missing.exists())
        store.admit(self.path, self.proposal())
        with sqlite3.connect(self.path) as connection:
            state = json.loads(connection.execute("SELECT payload FROM account_state").fetchone()[0])
            state["reserved_cash_usd"] = "0"
            connection.execute("UPDATE account_state SET payload=?", (json.dumps(state),))
        with self.assertRaisesRegex(ValueError, "reservations"):
            store.status(self.path)
        corrupt = self.fresh("corrupt")
        corrupt.write_bytes(b"not sqlite")
        with self.assertRaises(sqlite3.Error):
            store.status(corrupt)

    def test_existing_path_and_non_synthetic_or_nonflat_initialisation_fail(self):
        with self.assertRaises(FileExistsError):
            store.initialize(self.path, self.snapshot())
        for name, changes in (
                ("environment", {"environment": "paper"}),
                ("position", {"position_quantity": 1}),
                ("halt", {"mark": {"equity": "700", "deposits": "0", "withdrawals": "0"}})):
            path = Path(self.root.name) / f"bad-{name}.sqlite"
            with self.assertRaises(ValueError):
                store.initialize(path, self.snapshot(**changes))
            self.assertFalse(path.exists())

    def test_cli_walkthrough_and_bad_input_have_explicit_safe_modes(self):
        path = Path(self.root.name) / "cli.sqlite"
        snapshot = Path(self.root.name) / "snapshot.json"
        proposal = Path(self.root.name) / "proposal.json"
        snapshot.write_text(json.dumps(self.snapshot()))
        proposal.write_text(json.dumps(self.proposal()))
        output = io.StringIO()
        with contextlib.redirect_stdout(output):
            self.assertEqual(main(["order-init", str(path), str(snapshot)]), 0)
        self.assertFalse(json.loads(output.getvalue())["live_trading_enabled"])
        output = io.StringIO()
        with contextlib.redirect_stdout(output):
            self.assertEqual(main(["order-admit", str(path), str(proposal)]), 0)
        self.assertEqual(json.loads(output.getvalue())["outcome"], "reserved")
        bad = deepcopy(self.proposal("bad", version=1))
        bad["quantity"] = 0
        proposal.write_text(json.dumps(bad))
        output = io.StringIO()
        with contextlib.redirect_stdout(output), contextlib.redirect_stderr(io.StringIO()):
            self.assertEqual(main(["order-admit", str(path), str(proposal)]), 2)
        self.assertEqual(output.getvalue(), "")

    def test_shipped_examples_form_a_complete_synthetic_walkthrough(self):
        path = Path(self.root.name) / "examples.sqlite"
        snapshot = json.loads(Path("examples/order-account.json").read_text())
        proposal = json.loads(Path("examples/order-entry.json").read_text())
        self.assertEqual(store.initialize(path, snapshot)["policy_sha256"],
                         proposal["expected_policy_sha256"])
        result = store.admit(path, proposal)
        self.assertEqual(result["outcome"], "reserved")
        self.assertEqual(result["reservation"]["planned_loss_gbp"], "2.240")


if __name__ == "__main__":
    unittest.main()
