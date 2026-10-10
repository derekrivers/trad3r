from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy
import contextlib
import io
import json
from pathlib import Path
import sqlite3
import tempfile
import unittest

import test_order_allocations as allocation_tests
import test_order_reducing_dispatch as dispatch_tests
import test_order_sell_reconciliation as sell_tests
from trad3r import order_controls as controls
from trad3r import order_allocations as allocations
from trad3r import order_store as store
from trad3r import order_writer as writer
from trad3r import order_reducing_dispatch as dispatch
from trad3r import order_sell_reconciliation as sells
from trad3r.__main__ import main


class ProtectionControlTests(unittest.TestCase):
    def setUp(self):
        self.root = tempfile.TemporaryDirectory()
        self.addCleanup(self.root.cleanup)
        self.path = Path(self.root.name) / "orders.sqlite"
        self.base = allocation_tests.ReducingAllocationTests(methodName="runTest")
        allocations.initialize(self.path, self.base.account())

    def request(self, action="pause", identity="pause-one", at="2026-09-04T14:00:01Z", **changes):
        state = controls.status(self.path)
        request = {"schema": controls.SCHEMA, "control_id": identity,
                   "account_id": "synthetic-test", "environment": "synthetic",
                   "at": at, "action": action, "incident_id": None,
                   "expected_version": state["version"], "expected_sources": state["sources"]}
        request.update(changes)
        return request

    def position(self):
        fixture = sell_tests.SellReconciliationTests(methodName="runTest")
        fixture.setUp()
        self.addCleanup(fixture.doCleanups)
        self.path = fixture.path
        self.fixture = fixture
        return fixture

    def flat(self, identity="flat", at="2026-09-04T14:01:00Z", mark=None):
        execution = self.fixture.sell_execution()
        lot = self.fixture.lot(execution)
        snapshot = self.fixture.snapshot(identity, [execution], [self.fixture.sell_fee()],
                                         pending=[lot], at=at, mark=mark)
        return sells.apply(self.path, snapshot)

    def resolve_all(self, at="2026-09-04T14:01:02Z"):
        for incident in controls.status(self.path)["incidents"]:
            if incident["status"] == "open":
                request = self.request("resolve", "resolve-" + incident["incident_id"], at,
                                       incident_id=incident["incident_id"])
                controls._recover_for_test(self.path, request, owner_event_id="owner-" + request["control_id"])

    def test_pause_persists_blocks_entry_without_consuming_attempt_and_cli_is_read_only(self):
        request = self.request()
        controls.apply(self.path, request)
        with self.assertRaises(ValueError):
            store.admit(self.path, self.base.entry())
        account = store.status(self.path)
        self.assertEqual(account["attempts"], 0)
        self.assertIn("operator_paused", account["blocked_reasons"])
        before = self.path.read_bytes()
        with contextlib.redirect_stdout(io.StringIO()) as output:
            self.assertEqual(main(["order-control-status", str(self.path)]), 0)
        self.assertTrue(json.loads(output.getvalue())["operator_paused"])
        self.assertEqual(before, self.path.read_bytes())

    def test_flat_with_reserved_entry_is_unresolved_and_flatten_blocks_its_marker(self):
        store.admit(self.path, self.base.entry())
        writer.claim(self.path, {"schema": "order-writer-claim-v1", "claim_id": "claim",
                                "owner_id": "writer", "at": "2026-09-04T14:00:15Z", "expected_epoch": 0})
        report = controls.apply(self.path, self.request("flatten", "flatten", "2026-09-04T14:00:16Z"))
        self.assertEqual(report["facts"]["exposure"], "unresolved")
        self.assertEqual(report["facts"]["protection"], "unknown")
        self.assertTrue(report["facts"]["possible_entry"])
        adapter = writer.SyntheticAdapter()
        with self.assertRaises(ValueError):
            writer.dispatch_synthetic(self.path, {"schema": "order-submission-operation-v1",
                "operation_id": "submit", "intent_id": "entry-intent", "owner_id": "writer",
                "epoch": 1, "at": "2026-09-04T14:00:20Z", "expected_account_version": 1},
                "acknowledged", adapter)
        self.assertEqual(adapter.calls, 0)
        self.assertEqual(store.status(self.path)["attempts"], 1)
        with self.assertRaisesRegex(ValueError, "cannot be weakened"):
            controls.apply(self.path, self.request("cancel_entry_remainder", "weaken", "2026-09-04T14:00:17Z"))

    def test_pause_and_prior_halt_permit_evidenced_reductions_preserving_cash_and_attempts(self):
        fixture = self.position()
        fixture.dispatch_allocations()
        snapshot = fixture.snapshot("halt", sell_state="cancelled", position=2,
            mark={"equity": "989", "deposits": "0", "withdrawals": "0"})
        sells.apply(self.path, snapshot)
        controls.apply(self.path, self.request(at="2026-09-04T14:01:01Z"))
        managed = writer.status(self.path)
        writer.claim(self.path, {"schema": "order-writer-claim-v1", "claim_id": "reduce-again",
            "owner_id": "management-writer", "at": "2026-09-04T14:01:02Z", "expected_epoch": managed["epoch"]})
        fixture.allocate_exit("allocation-two", "exit-order-two", 2, "0.35", "2026-09-04T14:01:03Z")
        helper = dispatch_tests.ReducingDispatchTests(methodName="runTest")
        helper.path = self.path
        adapter = dispatch.SyntheticReducingAdapter()
        result = dispatch.dispatch_synthetic(self.path, helper.request("second", "allocation-two", "2026-09-04T14:01:04Z"), "acknowledged", adapter)
        self.assertEqual(result["operation"]["command"]["quantity"], 2)
        self.assertEqual(adapter.calls, 1)
        account = store.status(self.path)
        self.assertEqual(account["attempts"], 1)
        self.assertIn("daily", account["blocked_reasons"])
        self.assertTrue(controls.status(self.path)["operator_paused"])

    def test_verified_flat_pending_cash_pause_and_halt_survive_owner_recovery(self):
        self.position()
        controls.apply(self.path, self.request(at="2026-09-04T14:00:51Z"))
        self.flat(mark={"equity": "989", "deposits": "0", "withdrawals": "0"})
        report = controls.status(self.path)
        self.assertEqual((report["facts"]["exposure"], report["facts"]["protection"]), ("verified_flat", "not_required"))
        self.assertTrue(report["operator_paused"])
        before = store.status(self.path)
        writer_before = writer.status(self.path)
        self.resolve_all()
        request = self.request("resume", "resume", "2026-09-04T14:01:03Z")
        recovered = controls._recover_for_test(self.path, request, owner_event_id="owner-resume")
        self.assertFalse(recovered["operator_paused"])
        self.assertFalse(recovered["dispatch_authorized"])
        after = store.status(self.path)
        for field in ("assessment", "attempts", "settled_cash_usd", "pending_settlements", "policy_sha256", "version"):
            self.assertEqual(before[field], after[field])
        self.assertEqual(after["settled_cash_usd"], "299.65")
        self.assertEqual(after["unsettled_usd"], "198.65")
        for field in ("epoch", "version", "owner_id", "disarmed"):
            self.assertEqual(writer_before[field], writer.status(self.path)[field])
        duplicate = controls.apply(self.path, request)
        self.assertTrue(duplicate["duplicate"])
        self.assertEqual(duplicate["version"], recovered["version"])

    def test_untrusted_resume_and_owner_labels_or_reset_fields_cannot_clear_pause(self):
        controls.apply(self.path, self.request())
        request = self.request("resume", "resume", "2026-09-04T14:00:02Z")
        with self.assertRaisesRegex(ValueError, "owner control required"):
            controls.apply(self.path, request)
        for field, value in (("actor", "owner"), ("halt_reasons", []), ("session_start", "1000"), ("attempts", 0)):
            forged = {**request, field: value}
            with self.subTest(field=field), self.assertRaises(ValueError):
                controls.apply(self.path, forged)
        self.assertTrue(controls.status(self.path)["operator_paused"])

    def test_recovery_requires_new_complete_fresh_version_bound_evidence(self):
        self.position()
        self.flat()
        self.resolve_all()
        controls.apply(self.path, self.request(at="2026-09-04T14:01:03Z"))
        request = self.request("resume", "too-old", "2026-09-04T14:01:04Z")
        with self.assertRaisesRegex(ValueError, "new reconciliation"):
            controls._recover_for_test(self.path, request, owner_event_id="owner-old")
        self.flat("new-flat", "2026-09-04T14:01:05Z")
        request["at"] = "2026-09-04T14:01:06Z"
        with self.assertRaisesRegex(ValueError, "version or evidence changed"):
            controls._recover_for_test(self.path, request, owner_event_id="owner-stale")
        stale = self.request("resume", "stale", "2026-09-04T14:02:06Z")
        with self.assertRaisesRegex(ValueError, "fresh reconciliation"):
            controls._recover_for_test(self.path, stale, owner_event_id="owner-stale-time")
        future = self.request("resume", "future", "2026-09-04T14:01:04Z")
        with self.assertRaisesRegex(ValueError, "backwards"):
            controls._recover_for_test(self.path, future, owner_event_id="owner-future")
        valid = self.request("resume", "valid", "2026-09-04T14:01:06Z")
        self.assertFalse(controls._recover_for_test(self.path, valid, owner_event_id="owner-valid")["operator_paused"])

    def test_missing_protection_incident_latches_and_ordinary_flat_evidence_does_not_clear_it(self):
        self.position()
        incidents = controls.status(self.path)["incidents"]
        self.assertIn("protection_missing", [row["kind"] for row in incidents])
        self.flat()
        self.assertEqual(incidents, controls.status(self.path)["incidents"])
        incident = incidents[0]
        request = self.request("resolve", "resolve", "2026-09-04T14:01:01Z", incident_id=incident["incident_id"])
        result = controls._recover_for_test(self.path, request, owner_event_id="owner-resolution")
        self.assertEqual(result["incidents"][0]["status"], "resolved")
        self.assertEqual(result["incidents"][0]["resolution_id"], "resolve")
        self.assertFalse(result["dispatch_authorized"])

    def test_owner_event_cannot_authorize_a_second_recovery(self):
        self.position()
        controls.apply(self.path, self.request(at="2026-09-04T14:00:51Z"))
        self.flat()
        incident = controls.status(self.path)["incidents"][0]
        request = self.request("resolve", "resolve", "2026-09-04T14:01:01Z", incident_id=incident["incident_id"])
        controls._recover_for_test(self.path, request, owner_event_id="owner-once")
        resume = self.request("resume", "resume", "2026-09-04T14:01:02Z")
        with self.assertRaisesRegex(ValueError, "Owner control event reused"):
            controls._recover_for_test(self.path, resume, owner_event_id="owner-once")
        self.assertTrue(controls.status(self.path)["operator_paused"])

    def test_incomplete_evidence_and_manual_activity_remain_blocked(self):
        fixture = self.position()
        controls.apply(self.path, self.request(at="2026-09-04T14:00:51Z"))
        snapshot = fixture.snapshot("manual", sell_state="working", position=1)
        sells.apply(self.path, snapshot)
        report = controls.status(self.path)
        self.assertEqual(report["facts"]["exposure"], "unresolved")
        self.assertIn("reconciliation:position_quantity_mismatch", [row["kind"] for row in report["incidents"]])
        incident = report["incidents"][0]
        request = self.request("resolve", "bad-resolution", "2026-09-04T14:01:01Z", incident_id=incident["incident_id"])
        with self.assertRaisesRegex(ValueError, "complete fresh"):
            controls._recover_for_test(self.path, request, owner_event_id="owner-bad")
        self.assertTrue(controls.status(self.path)["operator_paused"])

    def test_exact_concurrent_pause_retries_once_changed_identity_latches(self):
        request = self.request()
        with ThreadPoolExecutor(max_workers=2) as pool:
            results = list(pool.map(lambda _: controls.apply(self.path, request), range(2)))
        self.assertEqual(sum(row["duplicate"] for row in results), 1)
        changed = {**request, "action": "flatten"}
        conflict = controls.apply(self.path, changed)
        self.assertEqual(conflict["outcome"], "identity_conflict")
        self.assertEqual(conflict["desired_action"], "hold")
        self.assertTrue(controls.apply(self.path, changed)["duplicate"])
        with self.assertRaises(ValueError):
            writer.claim(self.path, {"schema": "order-writer-claim-v1", "claim_id": "blocked",
                "owner_id": "writer", "at": "2026-09-04T14:00:02Z", "expected_epoch": 0})

    def test_changed_resolution_identity_is_a_blocking_conflict(self):
        self.position()
        self.flat()
        incident = controls.status(self.path)["incidents"][0]
        request = self.request("resolve", "resolve", "2026-09-04T14:01:01Z", incident_id=incident["incident_id"])
        controls._recover_for_test(self.path, request, owner_event_id="owner-resolve")
        changed = {**request, "incident_id": "different-incident"}
        result = controls.apply(self.path, changed)
        self.assertEqual(result["outcome"], "identity_conflict")
        self.assertIn("control_identity_conflict", [row["kind"] for row in result["incidents"]])

    def test_storage_failure_rolls_back_originating_evidence_and_incident(self):
        fixture = self.position()
        fixture.dispatch_allocations()
        snapshot = fixture.snapshot("fail", sell_state="working", position=1)
        before_account = store.status(self.path)
        before_controls = controls.status(self.path)
        with sqlite3.connect(self.path) as connection:
            connection.execute("CREATE TRIGGER fail_control BEFORE INSERT ON protection_control_events BEGIN SELECT RAISE(ABORT, 'injected'); END")
        with self.assertRaises(sqlite3.IntegrityError):
            sells.apply(self.path, snapshot)
        self.assertEqual(before_account, store.status(self.path))
        self.assertEqual(before_controls, controls.status(self.path))
        self.assertEqual(sells.history(self.path), [])

    def test_rehashed_projection_forgery_and_missing_observation_fail_closed(self):
        controls.apply(self.path, self.request())
        with sqlite3.connect(self.path) as connection:
            row = connection.execute("SELECT payload FROM protection_control_events WHERE sequence=1").fetchone()
            event = store.decode(row[0])
            event["state"]["operator_paused"] = False
            connection.execute("UPDATE protection_control_events SET payload=?,payload_sha256=? WHERE sequence=1", (store.pack(event), store.digest(event)))
            connection.execute("UPDATE protection_control_state SET payload=?", (store.pack(event["state"]),))
        for read in (store.status, writer.status, controls.status):
            with self.subTest(read=read), self.assertRaisesRegex(ValueError, "replay mismatch"):
                read(self.path)

    def test_deleted_observation_cannot_hide_new_account_evidence(self):
        store.admit(self.path, self.base.entry())
        with sqlite3.connect(self.path) as connection:
            initial = controls._initial(connection)
            connection.execute("DELETE FROM protection_control_events")
            connection.execute("UPDATE protection_control_state SET payload=?", (store.pack(initial),))
        with self.assertRaisesRegex(ValueError, "observation is missing"):
            store.status(self.path)

    def stop_position(self):
        fixture = allocation_tests.ReducingAllocationTests(methodName="runTest")
        fixture.setUp()
        self.addCleanup(fixture.doCleanups)
        self.path = fixture.path
        allocations.admit(self.path, fixture.request(
            purpose="protective_stop", allocation_id="allocation-exit", client_order_id="exit-order"))
        helper = dispatch_tests.ReducingDispatchTests(methodName="runTest")
        helper.path = self.path
        request = helper.request(order_type="stop", limit_price_usd=None, stop_price_usd="99.5")
        return helper, request

    def test_stop_rejection_requests_flatten_and_never_dispatches_a_fallback(self):
        helper, request = self.stop_position()
        adapter = dispatch.SyntheticReducingAdapter()
        dispatch.dispatch_synthetic(self.path, request, "rejected", adapter)
        report = controls.status(self.path)
        self.assertEqual(report["desired_action"], "flatten")
        self.assertEqual(report["facts"]["protection"], "rejected")
        self.assertIn("protective_stop_rejected", [row["kind"] for row in report["incidents"]])
        self.assertEqual(report["facts"]["committed_sell_quantity"], 0)
        self.assertEqual(adapter.calls, 1)
        self.assertFalse(report["dispatch_authorized"])
        self.assertTrue(dispatch.dispatch_synthetic(self.path, request, "rejected", adapter)["duplicate"])
        self.assertEqual(adapter.calls, 1)

    def test_stop_ack_is_pending_complete_working_proof_enables_incident_resolution(self):
        helper, request = self.stop_position()
        result = dispatch.dispatch_synthetic(self.path, request, "acknowledged")
        report = controls.status(self.path)
        self.assertEqual(report["facts"]["protection"], "pending")
        self.assertEqual(report["facts"]["covered_quantity"], 0)
        incident = report["incidents"][0]
        bad = self.request("resolve", "premature", "2026-09-04T14:00:56Z", incident_id=incident["incident_id"])
        with self.assertRaisesRegex(ValueError, "complete fresh"):
            controls._recover_for_test(self.path, bad, owner_event_id="premature-owner")
        fixture = sell_tests.SellReconciliationTests(methodName="runTest")
        fixture.path = self.path
        from trad3r import order_reconciliation
        fixture.entry_order_id = order_reconciliation.status(self.path)["order_projection"]["broker_order_id"]
        snapshot = fixture.snapshot("working-stop", sell_state="working", position=2, auto_dispatch=False)
        snapshot["orders"][1]["order_id"] = result["operation"]["broker_order_id"]
        sells.apply(self.path, snapshot)
        report = controls.status(self.path)
        self.assertEqual(report["facts"]["protection"], "active")
        self.assertEqual(report["facts"]["covered_quantity"], 2)
        self.assertEqual(report["incidents"][0]["status"], "open")
        self.resolve_all()
        self.assertTrue(all(row["status"] == "resolved" for row in controls.status(self.path)["incidents"]))
        terminal = fixture.snapshot("expired-stop", sell_state="cancelled", position=2,
                                    at="2026-09-04T14:01:03Z", auto_dispatch=False)
        terminal["orders"][1]["order_id"] = result["operation"]["broker_order_id"]
        sells.apply(self.path, terminal)
        report = controls.status(self.path)
        self.assertEqual(report["facts"]["exposure"], "verified_long")
        self.assertEqual(report["facts"]["protection"], "missing")
        self.assertEqual(report["facts"]["covered_quantity"], 0)
        self.assertTrue(any(row["status"] == "open" for row in report["incidents"]))

    def test_stop_lost_ack_holds_quantity_and_opens_an_incident(self):
        helper, request = self.stop_position()
        adapter = dispatch.SyntheticReducingAdapter()
        dispatch.dispatch_synthetic(self.path, request, "accept_then_timeout", adapter)
        report = controls.status(self.path)
        self.assertEqual(report["facts"]["protection"], "unknown")
        self.assertEqual(report["facts"]["committed_sell_quantity"], 2)
        self.assertIn("protection_unknown", [row["kind"] for row in report["incidents"]])
        self.assertEqual(adapter.calls, 1)
        self.assertEqual(report["desired_action"], "hold")

    def test_v3_remains_readable_and_cannot_accept_controls(self):
        path = Path(self.root.name) / "v3.sqlite"
        store.initialize(path, self.base.account())
        self.assertFalse(store.status(path)["blocked"])
        with self.assertRaisesRegex(ValueError, "fresh v4"):
            controls.apply(path, self.request())


if __name__ == "__main__":
    unittest.main()
