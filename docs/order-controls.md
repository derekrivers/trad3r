# Durable protection controls and synthetic owner recovery

P4.5 package F in [PR #41](https://github.com/derekrivers/trad3r/pull/41) adds `trad3r.order_controls` to freshly initialized version-4
synthetic order stores. It implements the control portions of X01/X02/X11/X14/
X15/X20–X22. Package G remains responsible for the complete integrated acceptance
matrix and lifecycle rehearsal.

## Journal and gates

`order-control DATABASE REQUEST.json` accepts restrictive `pause`, `hold`,
`cancel_entry_remainder` and `flatten` commands. `hold` cannot weaken an existing
objective, and `flatten` cannot be weakened to cancellation. Desired action is a
persisted objective: it blocks entry admission and entry submission, and reports
whether an entry remainder needs cancellation. It does not issue any order.
There is no automatic objective-reset or next-entry-episode transition.

`order-control-status DATABASE` and `order-control-history DATABASE` are read-only.
The request schema is `protection-control-request-v1`, with exactly `control_id`,
`account_id`, `environment: synthetic`, `at`, `action`, `incident_id`,
`expected_version` and `expected_sources` in addition to `schema`. Use null for
`incident_id` except on resolution requests. Status supplies the control version
and source bindings; each source binds a journal sequence and payload digest.

Pause, desired action, incidents and financial halts remain separate facts.
Pause and protection incidents block entries while allowing separately fenced,
evidenced management. Control identity conflicts also block new writer claims,
reducing allocations and reducing submission markers. Exact mapped cancellation
retains its existing independent checks. Claiming a writer never bypasses the
entry control check at the submission marker.

Each v4 write transaction appends a protection observation before commit when
its account, entry, sell, allocation, writer, cancellation or dispatch evidence
changes. The observation and originating operation either both commit or both
roll back. Protection replay reconstructs each historical observation from its
bounded retained journal prefixes. It verifies every control transition, source
digest, sequence, prior-state digest and materialized state. Missing observations
and rehashed false control projections fail closed on reopening. Reads cannot
repair the journal. The existing journals continue to validate their underlying
inputs and accounting independently.

Held exposure with missing, partial, unknown or rejected protection opens a
latched incident. Reconciliation contradictions retain their own incident causes.
A definitive protective-stop rejection requests flattening. Queued or acknowledged
stops have no confirmed coverage; only correlated working evidence contributes
coverage, and cancel-pending or uncertain stops retain their possible quantity.
A zero holding with a reserved or possibly live entry is unresolved, never verified
flat. An ordinary unsent entry reservation does not itself create a protection
incident that would prevent its first submission. Submission uncertainty does.

Protection status describes the retained evidence at its reported times, not a
fresh permission token. Freshness, fees, quantity and fencing remain enforced by
the allocation and dispatch paths. A later flat or protected snapshot cannot clear
an earlier incident. Flatness neither clears a pause/halt nor releases pending
sale proceeds.

## Owner recovery boundary

The production API and CLI cannot authenticate an owner and cannot originate a
recovery. `actor: owner`, reset fields and other extra payload fields are rejected.
The private `_recover_for_test` injection supplies a separately identified,
request-digest-bound **synthetic test control event**. It is deliberately not a
production authenticator or a permission to operate a paper/live account.
Connected owner authentication remains P5 work.

The recovery transition supports `resolve` for a specified open incident and
`resume` for an operator pause. Both bind the current control and all source
versions and require complete reconciliation no more than 60 seconds old, observed
strictly after the affected pause/incident. The evidence must prove either active
protection or verified flatness, with no unresolved writer evidence. Resume also
requires every incident to have been resolved. Identity conflicts and durable
accounting contradictions require a separate repair design and remain blocked;
ordinary fee-completeness incidents can be acknowledged once their cause is gone.

Recovery only appends control history. It does not dispatch, arm the writer,
change an objective, alter cash, settle proceeds, refund attempts, change limits,
renew day/week baselines, or clear any financial halt. Owner control event IDs
cannot authorize a second command. Exact command/resolution retries return the
current state before stale version checks; changed identity reuse appends a
blocking conflict without applying the changed action.

## Evidence and limits

Eighteen deterministic tests in `tests/test_order_controls.py` cover persisted pause/flatten gates, possible-entry
flatness, paused/halted reductions, pending cash and halt preservation through
recovery, forged authority/reset fields, new/fresh/version-bound recovery evidence,
incident retention, manual quantity contradictions, concurrent exact retries,
changed resolution identity, atomic rollback, coherent projection tampering,
missing observations, stop acknowledgement/rejection/uncertainty and v3 isolation.

All evidence is deterministic and synthetic. No broker, network endpoint, live
execution, production owner authentication, financial repair, cash release,
period transition, migration or later entry episode is introduced. Older v4 files
without the protection tables fail closed; use a fresh path for a new synthetic
fixture, never recreate an existing account to clear history. V3 behavior stays
unchanged. Existing-account migration requires separate reviewed work.
