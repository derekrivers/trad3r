from dataclasses import replace
from decimal import Decimal as D
import unittest

from trad3r.order_protection import (
    ENTRY, EXIT, STOP, EvaluationRequest, Incident, OrderProjection,
    ProtectionSnapshot, evaluate,
)


class OrderProtectionTests(unittest.TestCase):
    instrument = "synthetic:NASDAQ:AAPL:USD"

    def order(self, identity, purpose, state, quantity=2, executed=0, **changes):
        values = dict(
            order_id=identity, instrument_id=self.instrument, purpose=purpose,
            state=state, original_quantity=quantity, executed_quantity=executed,
            last_event_version=1, mapping_verified=True, evidence_complete=True,
        )
        values.update(changes)
        return OrderProjection(**values)

    def snapshot(self, **changes):
        values = dict(
            account_id="synthetic-test", environment="synthetic",
            instrument_id=self.instrument, account_version=7, evidence_version=4,
            execution_watermark=11,
            snapshot_id="snapshot-one", snapshot_at="2026-09-04T14:00:30Z",
            quantity=2, planned_stop_price_usd="99.5",
            quote_at="2026-09-04T14:00:20Z", fx_at="2026-09-04T14:00:20Z",
            exit_fee_allowance_usd="0.35", settled_cash_usd="399.65",
            quantity_verified=True, evidence_complete=True, order_inventory_complete=True,
            identity_consistent=True, store_valid=True, fee_evidence_bounded=True,
            fee_evidence_complete=True, writer_fenced=True, session_supported=True,
        )
        values.update(changes)
        return ProtectionSnapshot(**values)

    def request(self, **changes):
        values = dict(at="2026-09-04T14:00:40Z", expected_account_version=7,
                      expected_evidence_version=4)
        values.update(changes)
        return EvaluationRequest(**values)

    def test_x01_pause_and_halt_block_entry_but_not_verified_reduction(self):
        snapshot = self.snapshot(operator_paused=True, halt_reasons=("daily",))
        result = evaluate(snapshot, self.request(reduction_quantity=2,
                                                 reduction_fee_bound_usd="0.35"))
        self.assertEqual((result.exposure_state, result.protection_state),
                         ("verified_long", "missing"))
        self.assertFalse(result.entry_allowed)
        self.assertIn("operator_paused", result.entry_blocked_reasons)
        self.assertIn("halt:daily", result.entry_blocked_reasons)
        self.assertTrue(result.reduction_allowed)
        self.assertEqual((result.account_version, result.evidence_version,
                          result.execution_watermark, result.snapshot_id),
                         (7, 4, 11, "snapshot-one"))
        self.assertFalse(result.live_trading_enabled)

    def test_x02_flatness_is_independent_of_halts_pending_cash_and_pause(self):
        flat = evaluate(self.snapshot(quantity=0, operator_paused=True,
                                      halt_reasons=("daily",), settled_cash_usd="399.65"),
                        self.request())
        self.assertEqual((flat.exposure_state, flat.protection_state),
                         ("verified_flat", "not_required"))
        self.assertFalse(flat.entry_allowed)
        reserved_entry = self.order("entry-one", ENTRY, "reserved", quantity=1)
        unresolved = evaluate(self.snapshot(quantity=0, orders=(reserved_entry,)), self.request())
        self.assertEqual((unresolved.exposure_state, unresolved.protection_state),
                         ("unresolved", "unknown"))
        self.assertIsNone(unresolved.available_sell_quantity)

    def test_x03_planned_pending_active_partial_and_rejected_protection(self):
        missing = evaluate(self.snapshot(), self.request())
        pending_order = self.order("stop-one", STOP, "submitting", quantity=2,
                                   fee_allocation_usd="0.35")
        pending = evaluate(self.snapshot(orders=(pending_order,)), self.request())
        active_order = replace(pending_order, state="working", mapping_verified=True,
                               evidence_complete=True, confirmed_stop_price_usd=D("99.5"))
        active = evaluate(self.snapshot(orders=(active_order,)), self.request())
        partial = evaluate(self.snapshot(orders=(replace(active_order, original_quantity=1),)),
                           self.request())
        rejected_order = replace(
            pending_order, state="rejected", terminal_no_remainder_proved=True,
            last_event_version=2, fee_allocation_usd=D("0"))
        rejected = evaluate(self.snapshot(orders=(rejected_order,)), self.request())
        self.assertEqual([row.protection_state for row in (missing, pending, active, partial, rejected)],
                         ["missing", "pending", "active", "partial", "rejected"])
        self.assertEqual(active.covered_quantity, 2)
        tied_cancel = replace(rejected_order, order_id="stop-two", state="cancelled")
        tied = evaluate(self.snapshot(orders=(rejected_order, tied_cancel)), self.request())
        self.assertEqual(tied.protection_state, "missing")

    def test_x04_and_x05_all_possible_sells_share_quantity_and_fee_capacity(self):
        stop = self.order("stop-one", STOP, "unknown", fee_allocation_usd="0.35")
        blocked = evaluate(self.snapshot(orders=(stop,)),
                           self.request(reduction_quantity=1, reduction_fee_bound_usd="0"))
        self.assertEqual((blocked.protection_state, blocked.committed_sell_quantity,
                          blocked.available_sell_quantity), ("unknown", 2, 0))
        self.assertIn("sell_quantity_unavailable", blocked.reduction_blocked_reasons)

        split = (
            self.order("exit-one", EXIT, "reserved", quantity=1, fee_allocation_usd="0.15"),
            self.order("exit-two", EXIT, "reserved", quantity=1, fee_allocation_usd="0.20"),
        )
        exact = evaluate(self.snapshot(orders=split), self.request())
        self.assertEqual((exact.committed_sell_quantity, exact.available_exit_fee_usd), (2, "0.00"))
        reused = tuple(replace(order, fee_allocation_usd=D("0.35")) for order in split)
        conflict = evaluate(self.snapshot(orders=reused), self.request())
        self.assertIsNone(conflict.available_exit_fee_usd)
        self.assertIn("fee_allocation_conflict", conflict.reduction_blocked_reasons)

    def test_partial_sell_remainder_stays_committed_and_cancel_does_not_free_it(self):
        for state in ("partially_filled", "cancel_pending", "unknown"):
            with self.subTest(state=state):
                sell = self.order("exit-one", EXIT, state, executed=1,
                                  fee_allocation_usd="0.35")
                result = evaluate(self.snapshot(quantity=1, orders=(sell,)), self.request())
                self.assertEqual((result.committed_sell_quantity,
                                  result.available_sell_quantity), (1, 0))

    def test_x16_reduction_needs_fresh_complete_identity_evidence_but_cancel_does_not(self):
        target = self.order("stop-one", STOP, "unknown", fee_allocation_usd="0.35")
        incident = Incident("external-order", blocks_management=True)
        snapshot = self.snapshot(
            quantity_verified=False, identity_consistent=False,
            order_inventory_complete=False, snapshot_at="2026-09-04T13:58:00Z",
            quote_at="2026-09-04T13:58:00Z",
            fx_at="2026-09-04T14:01:00Z", writer_fenced=True,
            incidents=(incident,), orders=(target,))
        result = evaluate(snapshot, self.request(
            reduction_quantity=1, cancel_order_id="stop-one"))
        self.assertFalse(result.reduction_allowed)
        self.assertIn("quantity_unverified", result.reduction_blocked_reasons)
        self.assertIn("snapshot_stale", result.reduction_blocked_reasons)
        self.assertIn("quote_stale", result.reduction_blocked_reasons)
        self.assertIn("fx_future", result.reduction_blocked_reasons)
        self.assertIn("incident:external-order", result.reduction_blocked_reasons)
        self.assertTrue(result.cancellation_allowed)

        foreign = self.order("foreign-order", EXIT, "unknown", quantity=1,
                             instrument_id="synthetic:NASDAQ:MSFT:USD")
        known = self.order("known-order", STOP, "unknown", quantity=1)
        mixed = evaluate(self.snapshot(quantity=2, orders=(foreign, known)), self.request(
            reduction_quantity=1, cancel_order_id="known-order"))
        self.assertIn("identity_conflict", mixed.reduction_blocked_reasons)
        self.assertTrue(mixed.cancellation_allowed)

    def test_cancel_requires_current_versions_fencing_and_exact_mapping(self):
        target = self.order("entry-one", ENTRY, "working", mapping_verified=False)
        result = evaluate(self.snapshot(orders=(target,), writer_fenced=False), self.request(
            expected_account_version=6, cancel_order_id="entry-one"))
        self.assertEqual(result.cancellation_blocked_reasons, (
            "account_version_changed", "cancel_identity_unverified", "writer_not_fenced"))
        terminal = replace(target, state="cancelled", mapping_verified=True,
                           terminal_no_remainder_proved=True)
        result = evaluate(self.snapshot(orders=(terminal,)),
                          self.request(cancel_order_id="entry-one"))
        self.assertIn("cancel_target_terminal", result.cancellation_blocked_reasons)

        future = evaluate(self.snapshot(snapshot_at="2026-09-04T14:00:50Z", orders=(target,)),
                          self.request(cancel_order_id="entry-one"))
        self.assertIn("snapshot_future", future.cancellation_blocked_reasons)

    def test_management_incident_and_fee_bounds_fail_closed_without_hiding_quantity(self):
        result = evaluate(self.snapshot(
            incidents=(Incident("quantity-conflict", blocks_management=True),),
            fee_evidence_bounded=False),
            self.request(reduction_quantity=1, reduction_fee_bound_usd="0.10"))
        self.assertEqual(result.verified_quantity, 2)
        self.assertEqual(result.available_sell_quantity, 2)
        self.assertIn("incident:quantity-conflict", result.reduction_blocked_reasons)
        self.assertIn("fee_exposure_unbounded", result.reduction_blocked_reasons)

    def test_actual_fee_overrun_is_reported_and_never_creates_new_allowance(self):
        result = evaluate(self.snapshot(exit_fees_incurred_usd="0.45"),
                          self.request(reduction_quantity=1))
        self.assertIsNone(result.available_exit_fee_usd)
        self.assertIn("fee_allocation_conflict", result.reduction_blocked_reasons)

    def test_quantity_matrix_never_reports_negative_or_excess_reduction_capacity(self):
        for held in range(4):
            for committed in range(4):
                with self.subTest(held=held, committed=committed):
                    orders = (() if committed == 0 else (
                        self.order("exit-one", EXIT, "unknown", quantity=committed),))
                    result = evaluate(self.snapshot(quantity=held, orders=orders), self.request())
                    if committed > held or (held == 0 and committed):
                        self.assertEqual(result.exposure_state, "unresolved")
                        self.assertIsNone(result.available_sell_quantity)
                    else:
                        self.assertEqual(result.available_sell_quantity, held - committed)
        for requested in range(1, 5):
            with self.subTest(requested=requested):
                result = evaluate(self.snapshot(quantity=3),
                                  self.request(reduction_quantity=requested))
                self.assertEqual(result.reduction_allowed, requested <= 3)

    def test_desired_management_action_blocks_entry_without_blocking_reduction(self):
        result = evaluate(self.snapshot(desired_action="flatten"),
                          self.request(reduction_quantity=2, reduction_fee_bound_usd="0.35"))
        self.assertEqual(result.desired_action, "flatten")
        self.assertIn("desired_action:flatten", result.entry_blocked_reasons)
        self.assertTrue(result.reduction_allowed)

    def test_terminal_quantity_does_not_release_fee_only_reservations(self):
        for state in ("filled", "cancelled", "rejected"):
            with self.subTest(state=state):
                terminal = self.order(
                    "old-exit", EXIT, state, quantity=1,
                    executed=1 if state == "filled" else 0,
                    terminal_no_remainder_proved=state != "filled",
                    fee_allocation_usd="0.20")
                snapshot = self.snapshot(orders=(terminal,), fee_evidence_complete=False)
                result = evaluate(snapshot, self.request(
                    reduction_quantity=1, reduction_fee_bound_usd="0.16"))
                self.assertEqual(result.available_sell_quantity, 2)
                self.assertEqual(result.available_exit_fee_usd, "0.15")
                self.assertIn("exit_fee_allowance_unavailable", result.reduction_blocked_reasons)
                bounded = evaluate(snapshot, self.request(
                    reduction_quantity=1, reduction_fee_bound_usd="0.15"))
                self.assertTrue(bounded.reduction_allowed)
                flat = evaluate(replace(snapshot, quantity=0, fee_evidence_complete=True),
                                self.request())
                self.assertEqual(flat.exposure_state, "verified_flat")
                self.assertIn("outstanding_allocations", flat.entry_blocked_reasons)
                self.assertEqual(flat.available_exit_fee_usd, "0.15")

    def test_incomplete_order_evidence_cannot_free_quantity_or_prove_protection(self):
        for purpose in (ENTRY, EXIT, STOP):
            for state in ("working", "filled", "cancelled", "rejected"):
                for invalid in ("mapping_verified", "evidence_complete"):
                    with self.subTest(purpose=purpose, state=state, invalid=invalid):
                        order = self.order(
                            "unproven", purpose, state, quantity=2,
                            executed=2 if state == "filled" else 0,
                            terminal_no_remainder_proved=state in ("cancelled", "rejected"),
                            **{invalid: False})
                        result = evaluate(self.snapshot(orders=(order,)),
                                          self.request(reduction_quantity=1))
                        self.assertEqual(order.remainder, 2)
                        self.assertEqual((result.exposure_state, result.protection_state),
                                         ("unresolved", "unknown"))
                        self.assertIsNone(result.verified_quantity)
                        self.assertIsNone(result.available_sell_quantity)
                        self.assertFalse(result.reduction_allowed)

    def test_stale_future_and_invalid_proofs_never_report_active_coverage(self):
        stop = self.order("stop", STOP, "working", confirmed_stop_price_usd="99.5")
        for changes in (
                {"snapshot_at": "2026-09-04T13:59:39Z"},
                {"snapshot_at": "2026-09-04T14:00:41Z"},
                {"store_valid": False}, {"identity_consistent": False},
                {"evidence_complete": False}, {"quantity_verified": False}):
            with self.subTest(changes=changes):
                result = evaluate(self.snapshot(orders=(stop,), **changes), self.request())
                self.assertEqual(result.protection_state, "unknown")
                self.assertEqual(result.covered_quantity, 0)
                self.assertIsNone(result.verified_quantity)
        exact_age = evaluate(self.snapshot(orders=(stop,), snapshot_at="2026-09-04T13:59:40Z"),
                             self.request())
        self.assertEqual(exact_age.protection_state, "active")

    def test_other_cash_reservations_cannot_be_spent_on_exit_fees(self):
        snapshot = self.snapshot(settled_cash_usd="0.35", other_cash_allocations_usd="0.25")
        exact = evaluate(snapshot, self.request(reduction_quantity=1, reduction_fee_bound_usd="0.10"))
        self.assertTrue(exact.reduction_allowed)
        excess = evaluate(snapshot, self.request(reduction_quantity=1, reduction_fee_bound_usd="0.11"))
        self.assertIn("settled_cash_fee_unavailable", excess.reduction_blocked_reasons)
        conflict = evaluate(replace(snapshot, other_cash_allocations_usd="0.36"),
                            self.request(reduction_quantity=1))
        self.assertIn("fee_allocation_conflict", conflict.reduction_blocked_reasons)

    def test_flat_entry_gate_requires_current_versions_fencing_and_submission_evidence(self):
        self.assertTrue(evaluate(self.snapshot(quantity=0), self.request()).entry_allowed)
        for changes, reason in (
                ({"writer_fenced": False}, "writer_not_fenced"),
                ({"session_supported": False}, "unsupported_session"),
                ({"fee_evidence_bounded": False}, "fee_exposure_unbounded"),
                ({"exit_fees_incurred_usd": "0.36"}, "fee_allocation_conflict"),
                ({"quote_at": None}, "quote_missing"),
                ({"fx_at": "2026-09-04T13:59:39Z"}, "fx_stale")):
            with self.subTest(changes=changes):
                result = evaluate(self.snapshot(quantity=0, **changes), self.request())
                self.assertIn(reason, result.entry_blocked_reasons)
                self.assertFalse(result.entry_allowed)
        changed = evaluate(self.snapshot(quantity=0), self.request(
            expected_account_version=6, expected_evidence_version=3))
        self.assertIn("account_version_changed", changed.entry_blocked_reasons)
        self.assertIn("evidence_version_changed", changed.entry_blocked_reasons)

    def test_regular_session_bounds_apply_even_with_positive_session_assertion(self):
        for at, allowed in (
                ("2026-09-04T13:29:59Z", False), ("2026-09-04T13:30:00Z", True),
                ("2026-09-04T19:59:59Z", True), ("2026-09-04T20:00:00Z", False),
                ("2026-09-07T14:00:00Z", False), ("2026-09-05T14:00:00Z", False),
                ("2026-11-27T17:59:59Z", True), ("2026-11-27T18:00:00Z", False),
                ("2027-09-03T14:00:00Z", False)):
            with self.subTest(at=at):
                result = evaluate(self.snapshot(snapshot_at=at, quote_at=at, fx_at=at),
                                  self.request(at=at, reduction_quantity=1))
                self.assertEqual(result.reduction_allowed, allowed)
                self.assertEqual("unsupported_session" in result.reduction_blocked_reasons,
                                 not allowed)

    def test_known_entry_remainder_does_not_prevent_protecting_verified_holdings(self):
        entry = self.order("entry", ENTRY, "partially_filled", quantity=3, executed=2)
        snapshot = self.snapshot(orders=(entry,), other_cash_allocations_usd="100")
        result = evaluate(snapshot, self.request(reduction_quantity=2, reduction_fee_bound_usd="0.35"))
        self.assertTrue(result.reduction_allowed)
        self.assertFalse(result.entry_allowed)
        self.assertEqual(result.available_sell_quantity, 2)
        excess = evaluate(snapshot, self.request(reduction_quantity=3))
        self.assertIn("sell_quantity_unavailable", excess.reduction_blocked_reasons)

    def test_omitted_proofs_never_enable_permissions(self):
        snapshot = ProtectionSnapshot(
            account_id="synthetic-test", environment="synthetic", instrument_id=self.instrument,
            account_version=7, evidence_version=4, execution_watermark=11,
            snapshot_id="snapshot", snapshot_at="2026-09-04T14:00:30Z", quantity=2)
        result = evaluate(snapshot, self.request(reduction_quantity=1))
        self.assertFalse(result.entry_allowed)
        self.assertFalse(result.reduction_allowed)
        self.assertEqual(result.exposure_state, "unresolved")
        order = OrderProjection("unverified", self.instrument, EXIT, "filled", 1, 1, 1)
        self.assertEqual(order.remainder, 1)

    def test_invalid_structures_are_rejected_without_evaluation(self):
        with self.assertRaisesRegex(ValueError, "full quantity"):
            self.order("bad", EXIT, "filled", quantity=2, executed=1)
        with self.assertRaisesRegex(ValueError, "Terminal remainder proof"):
            self.order("bad-proof", EXIT, "working", quantity=1,
                       terminal_no_remainder_proved=True)
        with self.assertRaisesRegex(ValueError, "unique"):
            self.snapshot(orders=(self.order("same", EXIT, "reserved", quantity=1),
                                  self.order("same", EXIT, "reserved", quantity=1)))
        with self.assertRaisesRegex(ValueError, "typed"):
            evaluate({}, self.request())


if __name__ == "__main__":
    unittest.main()
