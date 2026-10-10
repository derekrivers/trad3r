# Project decisions

## D001 — Delivery baseline, 10 October 2026

The owner supplied `Trad3r_phased_delivery_plan.md` version 1.0 as the master plan
and asked to begin work on the VPS. Adopt its exact supplied bytes as
[project-plan.md](project-plan.md); source SHA-256
`a2ed0da8d426af8a030f354ef51b7143963021083cef58c8251ad5b7ebb63a97`.
After merge this repository file is canonical. Its starting-position and handoff
paragraphs describe the supplied snapshot; subsequent progress belongs in
[project-status.md](project-status.md). Older experiment records keep their meaning.

The initial work is Phase 0 and the synthetic offline Phase 1 package. Repository
review/CI/merge authority comes from `AGENTS.md`. No connected orders, account
opening, expenditure, live activation, halt reset or financial-policy change is
approved by this engineering request. All five agreed monetary limits are retained.

## D002 — Missing inputs, 10 October 2026

The full discretionary design v2 has not been supplied in the inspected locations.
Do not substitute unrelated ATLAS v2 archives. Reconciliation of that design is
blocked until its actual artifact is available; the master plan's stated product
boundaries suffice for independent offline work. No conflict with the implemented
financial limits was found in the supplied plan.

The owner confirmed during this session that no files have been transferred yet.
Private source/FX archives, three original experiment registrations, private cost
assumptions and result bundles were not found in the inspected host locations.
Recorded digests remain evidence of earlier runs, not verification of absent files.
Historical reproduction waits for those assets; use labelled synthetic fixtures
for host deployment and recovery. See the baseline inventory for search scope.

## D003 — Operational choices and remaining owner decisions

Use an unprivileged offline oneshot service, a root-owned pinned release and
explicit job starts. Preserve existing ATLAS workloads; add no timer or automatic
retry. Local backups/restores can be rehearsed without a purchased service, but
an approved off-host destination is still required for host-loss protection.
No new paid service has been selected. Existing VPS cost allocation remains open;
this engineering work does not assume hosting is free.

Broker/feed selection, connected-paper defaults/protocol, durable period changes,
model expenditure, alerts/off-host destinations and any live decision remain the
owner gates in the canonical plan. No spending or account secrets are needed to
finish the independent synthetic package.
