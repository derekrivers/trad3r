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

## D004 — Synthetic runtime and retention, 10 October 2026

Reuse the reviewed `ea44cc8` runtime and existing synthetic fixtures rather than
rebuilding delivered functionality. Each job pins its own release through a
systemd instance drop-in; future deployments must not repoint an active job to new
code. Root owns the release and the three read-only inputs. Host evidence is in
[vps-deployment-2026-10-10.md](vps-deployment-2026-10-10.md).

Keep the first local backup, original job, restore evidence and matching code.
No automatic pruning or recurring execution has been configured. Inspect storage
before explicit jobs/backups; pause new research at 80% disk use or less than
2 GiB free pending capacity review. These operational thresholds do not change
financial limits. Off-host storage, ongoing backup/alert operations and the VPS
cost allocation remain unresolved owner inputs; no paid destination was selected.

The subsequently supplied `trad3r-data-downloader.zip` contains only its README and
Python downloader, not the generated data package. It was inspected without
execution and does not satisfy the missing historical-input dependency.

## D005 — Original stock sample received, 10 October 2026

The owner subsequently supplied the generated stock archive. Its exact identity
and deterministic replay match the original records; see the
[intake evidence](stock-sample-intake-2026-10-10.md). Preserve it privately on ATLAS
and credit P0.5 with verified stock availability. Earlier absence findings describe
the state before this transfer. FX/combined history and original experiment files
remain missing; no hypothetical FX or replacement cost assumptions are authorised
as a substitute for the registered historical evidence.

## D006 — Development model routing and task register, 10 October 2026

Maintain one operational [task register](task-register.md) covering all 64 tasks in
the canonical plan. Start clear repeatable work with Luna, ordinary engineering and
research with Sol, and use Astra for the hardest architecture, accounting, risk,
order-uncertainty and phase-gate decisions. Escalate based on ambiguity, conflicting
evidence and failed approaches; once an Astra-reviewed contract is frozen, return
its scoped implementation to Sol where appropriate.

Model choice never changes task authority, financial limits, review requirements or
owner gates. Every PR still receives final-diff review, meaningful validation and
hosted CI on the reviewed SHA. The register governs development workflow only; P6.4
separately governs model/provider selection and expenditure for the trading agent.
