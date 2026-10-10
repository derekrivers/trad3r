from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy
import contextlib
import io
import json
from pathlib import Path
import sqlite3
import tempfile
import threading
import unittest

from trad3r import order_store as store
from trad3r import order_writer as writer
from trad3r.__main__ import main


class OrderWriterTests(unittest.TestCase):
    def setUp(self):
        self.root = tempfile.TemporaryDirectory()
        self.addCleanup(self.root.cleanup)
        self.path = Path(self.root.name) / "orders.sqlite"
        store.initialize(self.path, self.snapshot())
        store.admit(self.path, self.proposal())

    def snapshot(self):
        return {
            "schema": "synthetic-order-account-v1", "account_id": "synthetic-test",
            "environment": "synthetic", "at": "2026-09-04T14:00:00Z",
            "settled_cash_usd": "500", "position_quantity": 0,
            "mark": {"equity": "1000", "deposits": "0", "withdrawals": "0"},
            "session_start": {"equity": "1000", "deposits": "0", "withdrawals": "0"},
            "week_start": {"equity": "1000", "deposits": "0", "withdrawals": "0"},
            "ledger_version": 4, "risk_version": 7, "evidence_version": 2,
            "halt_reasons": [],
        }

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

    def claim(self, identity="one", owner="writer-a", epoch=0, at="2026-09-04T14:00:35Z"):
        return {
            "schema": "order-writer-claim-v1", "claim_id": f"claim-{identity}",
            "owner_id": owner, "at": at, "expected_epoch": epoch,
        }

    def operation(self, identity="one", intent="intent-one", owner="writer-a", epoch=1,
                  version=1, at="2026-09-04T14:00:40Z"):
        return {
            "schema": "order-submission-operation-v1", "operation_id": f"submit-{identity}",
            "intent_id": intent, "owner_id": owner, "epoch": epoch, "at": at,
            "expected_account_version": version,
        }

    def recovery(self, identity="one", owner="writer-a", epoch=1,
                 at="2026-09-04T14:00:50Z"):
        return {
            "schema": "order-writer-recovery-v1", "recovery_id": f"recovery-{identity}",
            "owner_id": owner, "epoch": epoch, "at": at,
        }

    def fresh(self, name):
        path = Path(self.root.name) / f"{name}.sqlite"
        store.initialize(path, self.snapshot())
        store.admit(path, self.proposal())
        return path

    def test_claim_is_idempotent_and_concurrent_owners_cannot_share_epoch(self):
        first = writer.claim(self.path, self.claim())
        duplicate = writer.claim(self.path, deepcopy(self.claim()))
        self.assertEqual((first["epoch"], first["owner_id"]), (1, "writer-a"))
        self.assertTrue(duplicate["duplicate"])
        self.assertEqual(len(writer.history(self.path)), 1)

        path = self.fresh("concurrent")
        def attempt(owner):
            try:
                return writer.claim(path, self.claim(owner, owner=owner))["owner_id"]
            except ValueError:
                return "blocked"
        with ThreadPoolExecutor(max_workers=2) as pool:
            results = list(pool.map(attempt, ("writer-a", "writer-b")))
        self.assertEqual(results.count("blocked"), 1)
        self.assertEqual(writer.status(path)["epoch"], 1)
        self.assertEqual(len(writer.history(path)), 1)

    def test_dispatch_marker_commits_before_one_acknowledged_adapter_call(self):
        writer.claim(self.path, self.claim())
        adapter = writer.SyntheticAdapter()
        first = writer.dispatch_synthetic(self.path, self.operation(), "acknowledged", adapter)
        again = writer.dispatch_synthetic(self.path, deepcopy(self.operation()), "acknowledged", adapter)
        self.assertEqual(first["outcome"], "acknowledged")
        self.assertEqual(first["submission"]["broker_order_id"],
                         again["submission"]["broker_order_id"])
        self.assertTrue(again["duplicate"])
        self.assertEqual(adapter.calls, 1)
        self.assertEqual([event["kind"] for event in writer.history(self.path)],
                         ["writer_claimed", "submission_marked", "submission_result"])
        self.assertEqual(store.status(self.path)["reserved_cash_usd"], "100.75")

    def test_concurrent_exact_dispatches_make_only_one_adapter_call(self):
        writer.claim(self.path, self.claim())
        started = threading.Event()
        release = threading.Event()
        class BlockingAdapter(writer.SyntheticAdapter):
            def submit(self, command, outcome):
                self.calls += 1
                started.set()
                if not release.wait(3):
                    raise AssertionError("concurrent retry did not reach its marker read")
                return {"outcome": "acknowledged", "broker_order_id": "synthetic-concurrent"}
        adapter = BlockingAdapter()
        with ThreadPoolExecutor(max_workers=2) as pool:
            first = pool.submit(
                writer.dispatch_synthetic, self.path, self.operation(), "acknowledged", adapter)
            self.assertTrue(started.wait(3))
            second = pool.submit(
                writer.dispatch_synthetic, self.path, deepcopy(self.operation()),
                "acknowledged", adapter)
            second_result = second.result(timeout=3)
            release.set()
            first_result = first.result(timeout=3)
        self.assertEqual(first_result["outcome"], "acknowledged")
        self.assertEqual(second_result["outcome"], "submitting")
        self.assertTrue(second_result["duplicate"])
        self.assertEqual(adapter.calls, 1)

    def test_lost_acknowledgement_is_unknown_disarmed_and_never_retried(self):
        writer.claim(self.path, self.claim())
        adapter = writer.SyntheticAdapter()
        result = writer.dispatch_synthetic(
            self.path, self.operation(), "accept_then_timeout", adapter)
        self.assertEqual(result["outcome"], "unknown")
        self.assertTrue(result["writer"]["disarmed"])
        self.assertEqual(result["writer"]["unresolved_reasons"], ["submission_unknown"])
        retry = writer.dispatch_synthetic(
            self.path, deepcopy(self.operation()), "acknowledged", adapter)
        self.assertEqual(retry["outcome"], "unknown")
        self.assertFalse(retry["should_call_adapter"])
        self.assertEqual(adapter.calls, 1)
        self.assertEqual(store.status(self.path)["reserved_cash_usd"], "100.75")

    def test_restart_recovery_turns_committed_marker_unknown_and_fences_old_owner(self):
        writer.claim(self.path, self.claim())
        marked = writer.mark_submission(self.path, self.operation())
        self.assertTrue(marked["should_call_adapter"])
        recovered = writer.recover(self.path, self.recovery())
        self.assertEqual(recovered["submissions"][0]["state"], "unknown")
        self.assertIsNone(recovered["owner_id"])
        self.assertTrue(recovered["disarmed"])
        self.assertTrue(writer.recover(self.path, deepcopy(self.recovery()))["duplicate"])
        adapter = writer.SyntheticAdapter()
        retry = writer.dispatch_synthetic(self.path, self.operation(), "acknowledged", adapter)
        self.assertEqual(retry["outcome"], "unknown")
        self.assertEqual(adapter.calls, 0)
        with self.assertRaisesRegex(ValueError, "unresolved"):
            writer.claim(self.path, self.claim("next", owner="writer-b", epoch=1))

    def test_clean_recovery_allows_a_new_higher_epoch_and_rejects_old_fence(self):
        writer.claim(self.path, self.claim())
        recovered = writer.recover(self.path, self.recovery())
        self.assertEqual(recovered["unresolved_reasons"], [])
        claimed = writer.claim(self.path, self.claim(
            "two", owner="writer-b", epoch=1, at="2026-09-04T14:00:55Z"))
        self.assertEqual((claimed["epoch"], claimed["owner_id"]), (2, "writer-b"))
        with self.assertRaisesRegex(ValueError, "ownership|fencing"):
            writer.mark_submission(self.path, self.operation())

    def test_failed_marker_commit_rolls_back_queue_and_preserves_writer_claim(self):
        writer.claim(self.path, self.claim())
        with sqlite3.connect(self.path) as connection:
            connection.execute(
                "CREATE TRIGGER fail_marker BEFORE INSERT ON writer_events "
                "WHEN NEW.kind='submission_marked' "
                "BEGIN SELECT RAISE(ABORT, 'injected marker failure'); END"
            )
        connection.close()
        with self.assertRaises(sqlite3.Error):
            writer.mark_submission(self.path, self.operation())
        report = writer.status(self.path)
        self.assertEqual(report["version"], 1)
        self.assertEqual(report["submissions"], [])
        self.assertTrue(report["dispatch_allowed"])

    def test_failed_result_commit_leaves_marker_and_retry_never_calls_adapter(self):
        writer.claim(self.path, self.claim())
        path = self.path
        class FailAfterAccept:
            calls = 0
            def submit(self, command, outcome):
                self.calls += 1
                connection = sqlite3.connect(path)
                connection.execute(
                    "CREATE TRIGGER fail_result BEFORE INSERT ON writer_events "
                    "WHEN NEW.kind='submission_result' "
                    "BEGIN SELECT RAISE(ABORT, 'injected result failure'); END"
                )
                connection.commit()
                connection.close()
                return {"outcome": "acknowledged", "broker_order_id": "accepted-but-uncommitted"}
        adapter = FailAfterAccept()
        with self.assertRaises(sqlite3.Error):
            writer.dispatch_synthetic(self.path, self.operation(), "acknowledged", adapter)
        self.assertEqual(writer.status(self.path)["submissions"][0]["state"], "submitting")
        retry = writer.dispatch_synthetic(self.path, self.operation(), "acknowledged", adapter)
        self.assertEqual(retry["outcome"], "submitting")
        self.assertEqual(adapter.calls, 1)

    def test_mutated_submission_projection_fails_closed_against_event_replay(self):
        writer.claim(self.path, self.claim())
        writer.dispatch_synthetic(self.path, self.operation(), "acknowledged")
        connection = sqlite3.connect(self.path)
        raw = connection.execute("SELECT payload FROM submissions").fetchone()[0]
        payload = json.loads(raw)
        payload["broker_order_id"] = "synthetic-mutated"
        connection.execute(
            "UPDATE submissions SET broker_order_id=?,payload=?",
            (payload["broker_order_id"], json.dumps(payload)),
        )
        connection.commit()
        connection.close()
        with self.assertRaisesRegex(ValueError, "projection"):
            writer.status(self.path)

    def test_expired_unsent_authority_is_cancelled_and_resources_release_once(self):
        writer.claim(self.path, self.claim())
        operation = self.operation(at="2026-09-04T14:01:15Z")
        adapter = writer.SyntheticAdapter()
        result = writer.dispatch_synthetic(self.path, operation, "acknowledged", adapter)
        self.assertEqual(result["outcome"], "cancelled")
        self.assertEqual(adapter.calls, 0)
        account = store.status(self.path)
        self.assertEqual((account["version"], account["attempts"], account["reserved_cash_usd"]),
                         (2, 1, "0"))
        duplicate = writer.dispatch_synthetic(self.path, deepcopy(operation), "acknowledged", adapter)
        self.assertTrue(duplicate["duplicate"])
        self.assertEqual(adapter.calls, 0)
        admission = store.admit(self.path, self.proposal())
        self.assertEqual(admission["outcome"], "cancelled")
        self.assertEqual(admission["reasons"], ["expired_authority"])
        self.assertEqual([event.get("reason") for event in store.history(self.path)],
                         [None, "expired_authority"])

    def test_stale_account_version_wrong_owner_and_unclaimed_dispatch_fail_without_marker(self):
        unclaimed = self.fresh("unclaimed")
        with self.assertRaisesRegex(ValueError, "disarmed"):
            writer.mark_submission(unclaimed, self.operation())
        writer.claim(self.path, self.claim())
        with self.assertRaisesRegex(ValueError, "ownership|fencing"):
            writer.mark_submission(self.path, self.operation(owner="writer-b"))
        store.admit(self.path, self.proposal("two", version=1))
        with self.assertRaisesRegex(ValueError, "Account version changed"):
            writer.mark_submission(self.path, self.operation(version=1))
        self.assertEqual(len(writer.history(self.path)), 1)

    def test_changed_operation_identity_is_a_durable_disarming_incident(self):
        writer.claim(self.path, self.claim())
        writer.mark_submission(self.path, self.operation())
        changed = self.operation(at="2026-09-04T14:00:41Z")
        result = writer.mark_submission(self.path, changed)
        self.assertEqual(result["outcome"], "identity_conflict")
        self.assertTrue(result["writer"]["disarmed"])
        self.assertIn("writer_identity_conflict", result["writer"]["unresolved_reasons"])
        self.assertEqual(writer.status(self.path)["submissions"][0]["state"], "submitting")
        self.assertTrue(writer.mark_submission(self.path, deepcopy(changed))["duplicate"])
        self.assertEqual(len(writer.history(self.path)), 3)

    def test_pre_writer_database_remains_readable_but_requires_explicit_writer_migration(self):
        path = self.fresh("legacy")
        connection = sqlite3.connect(path)
        for table in ("writer_events", "submissions", "writer_state", "reservation_releases"):
            connection.execute(f"DROP TABLE {table}")
        connection.execute("PRAGMA user_version=1")
        connection.commit()
        connection.close()
        self.assertEqual(store.status(path)["attempts"], 1)
        self.assertTrue(store.admit(path, self.proposal())["duplicate"])
        with self.assertRaisesRegex(ValueError, "explicit P4.3 writer migration"):
            writer.status(path)

    def test_definitive_rejection_still_preserves_resources_for_reconciliation(self):
        writer.claim(self.path, self.claim())
        result = writer.dispatch_synthetic(self.path, self.operation(), "rejected")
        self.assertEqual(result["outcome"], "rejected")
        self.assertTrue(result["writer"]["disarmed"])
        self.assertIn("submission_rejected", result["writer"]["unresolved_reasons"])
        self.assertEqual(store.status(self.path)["reserved_cash_usd"], "100.75")

    def test_cli_and_shipped_inputs_cover_the_synthetic_submission_boundary(self):
        path = Path(self.root.name) / "cli.sqlite"
        snapshot = Path(self.root.name) / "account.json"
        proposal = Path(self.root.name) / "proposal.json"
        claim = Path(self.root.name) / "claim.json"
        operation = Path(self.root.name) / "operation.json"
        for target, payload in ((snapshot, self.snapshot()), (proposal, self.proposal()),
                                (claim, self.claim()), (operation, self.operation())):
            target.write_text(json.dumps(payload))
        for args in (("order-init", str(path), str(snapshot)),
                     ("order-admit", str(path), str(proposal)),
                     ("order-writer-claim", str(path), str(claim))):
            with contextlib.redirect_stdout(io.StringIO()):
                self.assertEqual(main(list(args)), 0)
        output = io.StringIO()
        with contextlib.redirect_stdout(output):
            self.assertEqual(main(["order-dispatch-synthetic", str(path), str(operation),
                                   "--outcome", "accept_then_timeout"]), 0)
        result = json.loads(output.getvalue())
        self.assertEqual(result["outcome"], "unknown")
        self.assertFalse(result["live_trading_enabled"])

        examples = Path("examples")
        self.assertEqual(json.loads((examples / "order-writer-claim.json").read_text())["schema"],
                         "order-writer-claim-v1")
        self.assertEqual(json.loads((examples / "order-submission.json").read_text())["schema"],
                         "order-submission-operation-v1")
        example_path = Path(self.root.name) / "examples.sqlite"
        store.initialize(example_path, json.loads((examples / "order-account.json").read_text()))
        store.admit(example_path, json.loads((examples / "order-entry.json").read_text()))
        writer.claim(example_path, json.loads((examples / "order-writer-claim.json").read_text()))
        example_result = writer.dispatch_synthetic(
            example_path, json.loads((examples / "order-submission.json").read_text()),
            "acknowledged")
        self.assertEqual(example_result["outcome"], "acknowledged")


if __name__ == "__main__":
    unittest.main()
