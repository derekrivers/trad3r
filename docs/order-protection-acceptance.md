# P4.5 integrated acceptance evidence

Package G adds 14 focused rehearsals and exercises the [protection contract](order-protection.md) against freshly
initialized v4 SQLite stores, fenced synthetic writers and cumulative invented
broker evidence. Run all evidence with:

```sh
python3 -m unittest discover -s tests -v
```

The focused rehearsal command is:

```sh
python3 -m unittest discover -s tests -p test_order_protection_rehearsal.py -v
```

Every request/evidence application opens the real store and validates its durable
history. Concurrent requests use independent connections. Crash cases terminate a
separate interpreter with `os._exit` before the marker, after its commit, or after
a synthetic adapter durably records acceptance outside SQLite. A SQLite trigger
also aborts result persistence after acceptance. Reopening and retrying the exact
request must never repeat a possibly sent call. These tests do not simulate power
loss, disk-controller behavior, a real broker or production owner authentication.

## Protection scenarios

Test names below omit the common `test_` prefix. Module links identify the source;
each row names executable evidence, rather than crediting the pure evaluator alone.

| ID | Store/writer integration evidence |
| --- | --- |
| X01 | [rehearsal](../tests/test_order_protection_rehearsal.py): `numeric_entry_cancel_stop_cancel_exit_preserves_pause_halt_and_attempts`; [controls](../tests/test_order_controls.py): `pause_and_prior_halt_permit_evidenced_reductions_preserving_cash_and_attempts`, `pause_persists_blocks_entry_without_consuming_attempt_and_cli_is_read_only` |
| X02 | [controls](../tests/test_order_controls.py): `verified_flat_pending_cash_pause_and_halt_survive_owner_recovery`, `flat_with_reserved_entry_is_unresolved_and_flatten_blocks_its_marker`; [rehearsal](../tests/test_order_protection_rehearsal.py): `one_share_fee_revision_and_cutoff_restart_keep_pending_unspendable` |
| X03 | [controls](../tests/test_order_controls.py): `stop_ack_is_pending_complete_working_proof_enables_incident_resolution`; [rehearsal](../tests/test_order_protection_rehearsal.py): `stop_uncertainty_blocks_replacement_but_rejection_allows_fresh_exit` |
| X04 | [rehearsal](../tests/test_order_protection_rehearsal.py): `concurrent_distinct_full_exits_reserve_and_dispatch_exactly_one`; [allocations](../tests/test_order_allocations.py): `stop_and_exit_share_quantity_and_fee_without_consuming_entry_attempts`, `two_full_fee_requests_cannot_reuse_the_allowance`; [sell reconciliation](../tests/test_order_sell_reconciliation.py): `two_sell_orders_conserve_quantity_fees_and_pending_proceeds` |
| X05 | [rehearsal](../tests/test_order_protection_rehearsal.py): `stop_uncertainty_blocks_replacement_but_rejection_allows_fresh_exit`, `numeric_entry_cancel_stop_cancel_exit_preserves_pause_halt_and_attempts` |
| X06 | [sell reconciliation](../tests/test_order_sell_reconciliation.py): `partial_then_full_sell_moves_holdings_and_commitment_without_crediting_cash`, `exact_duplicate_and_new_envelope_do_not_double_count_execution`; [rehearsal](../tests/test_order_protection_rehearsal.py): `stop_fill_during_cancel_dispatches_only_verified_residual` |
| X07 | [rehearsal](../tests/test_order_protection_rehearsal.py): `entry_cancel_resolves_across_entry_to_reducing_evidence_boundary`; [rehearsal](../tests/test_order_protection_rehearsal.py): `partial_entry_then_fill_before_cancel_response_preserves_two_shares`; [cancellation](../tests/test_order_cancellation.py): `partial_sell_during_cancel_keeps_residual_commitment` |
| X08 | [cancellation](../tests/test_order_cancellation.py): `fill_before_response_makes_cancel_moot_and_retains_response`; [rehearsal](../tests/test_order_protection_rehearsal.py): `stop_fill_during_cancel_dispatches_only_verified_residual` (both residual and fully filled branches) |
| X09 | [cancellation](../tests/test_order_cancellation.py): `rejected_working_and_bare_denial_have_distinct_safety_states` |
| X10 | [rehearsal](../tests/test_order_protection_rehearsal.py): `process_death_and_result_rollback_never_repeat_adapter_calls` (four fault boundaries for cancellation and reducing dispatch); [cancellation](../tests/test_order_cancellation.py): `result_commit_failure_rolls_back_and_replay_corruption_fails_closed` |
| X11 | [rehearsal](../tests/test_order_protection_rehearsal.py): `stop_uncertainty_blocks_replacement_but_rejection_allows_fresh_exit`; [controls](../tests/test_order_controls.py): `stop_rejection_requests_flatten_and_never_dispatches_a_fallback` |
| X12 | [rehearsal](../tests/test_order_protection_rehearsal.py): `stop_uncertainty_blocks_replacement_but_rejection_allows_fresh_exit`; [controls](../tests/test_order_controls.py): `stop_lost_ack_holds_quantity_and_opens_an_incident` |
| X13 | [rehearsal](../tests/test_order_protection_rehearsal.py): `stop_fill_during_cancel_dispatches_only_verified_residual`, `numeric_entry_cancel_stop_cancel_exit_preserves_pause_halt_and_attempts` |
| X14 | [rehearsal](../tests/test_order_protection_rehearsal.py): `late_cancelled_stop_fill_retains_replacement_and_capacity_incident` |
| X15 | [rehearsal](../tests/test_order_protection_rehearsal.py): `numeric_entry_cancel_stop_cancel_exit_preserves_pause_halt_and_attempts`; [allocations](../tests/test_order_allocations.py): `exact_retry_precedes_stale_versions_and_changed_reuse_latches_incident`; [cancellation](../tests/test_order_cancellation.py): `exact_duplicate_never_calls_adapter_twice_and_changed_identity_latches`; [controls](../tests/test_order_controls.py): `verified_flat_pending_cash_pause_and_halt_survive_owner_recovery`, `changed_resolution_identity_is_a_blocking_conflict` |
| X16 | [rehearsal](../tests/test_order_protection_rehearsal.py): `stale_evidence_blocks_reduction_but_mapped_cancellation_needs_no_quote`; [allocations](../tests/test_order_allocations.py): `stale_future_and_other_period_evidence_cannot_reserve`, `stale_bindings_and_wrong_writer_fence_write_nothing`; [dispatch](../tests/test_order_reducing_dispatch.py): `stale_versions_expiry_prices_and_fence_fail_before_marker`, `order_without_durable_dispatch_marker_is_external_activity`; [cancellation](../tests/test_order_cancellation.py): `stale_fencing_versions_expiry_and_unknown_target_fail_before_marker`; cancellation requests have no quote/free-capacity input |
| X17 | [rehearsal](../tests/test_order_protection_rehearsal.py): `numeric_entry_cancel_stop_cancel_exit_preserves_pause_halt_and_attempts`, `missing_and_provisional_one_share_fee_retain_reservation_until_final` |
| X18 | [rehearsal](../tests/test_order_protection_rehearsal.py): `one_share_fee_revision_and_cutoff_restart_keep_pending_unspendable` |
| X19 | [rehearsal](../tests/test_order_protection_rehearsal.py): `one_share_fee_revision_and_cutoff_restart_keep_pending_unspendable`; [settlement](../tests/test_settlement.py): `t1_weekdays_weekends_and_all_scheduled_holiday_spans`, `closed_trade_dates_and_unknown_years_fail_closed`, `release_cutoff_is_midnight_after_due_day_in_new_york` (pure calendar evidence; ledger release tests do not authorize durable-store release) |
| X20 | [rehearsal](../tests/test_order_protection_rehearsal.py): `trade_bust_or_position_mismatch_retains_evidence_without_quantity_permission`; [sell reconciliation](../tests/test_order_sell_reconciliation.py): `changed_execution_manual_sell_and_overfill_are_retained_incidents`, `pending_mismatch_and_incomplete_snapshot_change_no_account_fact`; [controls](../tests/test_order_controls.py): `incomplete_evidence_and_manual_activity_remain_blocked` |
| X21 | [controls](../tests/test_order_controls.py): `untrusted_resume_and_owner_labels_or_reset_fields_cannot_clear_pause`, `recovery_requires_new_complete_fresh_version_bound_evidence`, `owner_event_cannot_authorize_a_second_recovery`, `verified_flat_pending_cash_pause_and_halt_survive_owner_recovery` |
| X22 | [rehearsal](../tests/test_order_protection_rehearsal.py): `stop_gap_and_day_expiry_do_not_infer_flatness`; [sell reconciliation](../tests/test_order_sell_reconciliation.py): `working_unknown_and_absent_sell_evidence_never_frees_reserved_shares` |
| X23 | [rehearsal](../tests/test_order_protection_rehearsal.py): `terminal_entry_cancellation_and_projection_commit_atomically`; [rehearsal](../tests/test_order_protection_rehearsal.py): `process_death_and_result_rollback_never_repeat_adapter_calls`; [dispatch](../tests/test_order_reducing_dispatch.py): `stale_versions_expiry_prices_and_fence_fail_before_marker`, `result_commit_failure_retains_marker_and_corruption_blocks_reads`; [controls](../tests/test_order_controls.py): `storage_failure_rolls_back_originating_evidence_and_incident`, `rehashed_projection_forgery_and_missing_observation_fail_closed`, `deleted_intermediate_observation_cannot_be_hidden_by_rehashing` |
| X24 | [rehearsal](../tests/test_order_protection_rehearsal.py): `numeric_entry_cancel_stop_cancel_exit_preserves_pause_halt_and_attempts` |

The expanded full suite has a ten-minute hosted-job timeout to accommodate the
process-boundary and replay-heavy rehearsals on Windows as well as Linux.

The numeric trace checks $200.80 / £160.08 / £1.52 admission reservations, the
$100.40 live-entry reserve, the $0.35 terminal-entry reserve, one-share stop/exit
capacity exclusion, and terminal $399.65 settled plus $99.15 pending. There is
one entry submission, one stop, one exit and two cancellation calls across exact
retries. Pause, the daily loss halt and the consumed entry attempt survive.
The fee-revision trace changes pending cash once to $99.05 while leaving settled
cash unchanged. Reopening in another process does not release it; a dated
cross-period application at the research cutoff is refused.

## Overlapping order-lifecycle vectors

These mappings refine [O01–O14](order-lifecycle.md#synthetic-acceptance-cases).
They establish the listed synthetic portions, not completion of every future
Phase 4 fault or connected-broker case.

| Vector | Executable overlap |
| --- | --- |
| O01 | [entry reconciliation](../tests/test_order_reconciliation.py): `cumulative_partial_then_fill_updates_cash_position_fee_and_reservation_once`; rehearsal X07/X24 |
| O02 | X15; [entry reconciliation](../tests/test_order_reconciliation.py): `snapshot_identity_conflict_is_durable_and_disarming` |
| O05 | X10/X23; [writer](../tests/test_order_writer.py): `failed_marker_commit_rolls_back_queue_and_preserves_writer_claim`, `failed_result_commit_leaves_marker_and_retry_never_calls_adapter`, `restart_recovery_turns_committed_marker_unknown_and_fences_old_owner` |
| O06 | X12; [entry reconciliation](../tests/test_order_reconciliation.py): `empty_order_snapshot_never_resolves_a_lost_acknowledgement` |
| O07 | X07/X13/X24: partial entry and stop fills across cancellation, freshly proved residuals |
| O08 | X08/X09: fill-before-response, retained late receipt, rejected-working versus bare denial |
| O09 | X14; [dispatch](../tests/test_order_reducing_dispatch.py): `late_rejection_after_working_evidence_latches_a_conflict` |
| O10 | X06/X17/X18/X20: execution deduplication, fee revisions and contradictory evidence |
| O11 | X10/X23: process death, transactional failure, integrity and fencing checks |
| O12 | X04/X05/X11/X12: concurrent exits, rejection, uncertain protective stop |
| O13 | [dispatch](../tests/test_order_reducing_dispatch.py): `acknowledged_broker_identity_mismatch_fails_closed`, `order_without_durable_dispatch_marker_is_external_activity`; X20 |
| O14 | X15/X23: exact retries have no new call; invalid authority cannot mark a command |

P4.6 durable day/week policy and settlement release, existing-account migration,
external incident repair, production owner authentication and connected paper
remain separate work. P4.7 retains broader system fault testing; package G does
not claim anti-rollback protection for a restored stale database, a real broker
reconciliation protocol, or the full Phase 4 exit gate.
