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

## D007 — Bounded Massive stock/FX access check, 10 October 2026

Using the existing root-managed credential, a single bounded read-only acquisition
returned complete 20-session stock coverage for AAPL, MSFT and F and a separate
GBP/USD completed-bar proxy. The archive and validation evidence are private; its
identity and limitations are recorded in [the intake report](massive-fx-intake-2026-10-10.md).
This verifies access and structural coverage only. It does not reconstruct the
missing original combined archive, qualify the history, establish broker costs or
authorize paid services, account actions or live execution.

## D008 — Durable order lifecycle definition, 10 October 2026

Freeze [order-lifecycle-v1](order-lifecycle.md) as P4.1's implementation contract.
Persist stable intent, client-order, operation and execution identities. Treat a
possibly sent submission as unknown until reconciled; never blindly resubmit.
Keep execution quantity, account exposure, reservation release and reconciliation
separate from the order-status label. Terminal status does not establish flatness
or settled cash. Preserve late evidence, all halts and every consumed attempt slot.

This is a definition milestone, not an implemented durable execution system.
P4.2 starts with a reviewed single-store transaction and allocation design;
P4.3–P4.5 supply writer, reconciliation and protection. The existing diagnostic
risk store remains unchanged. No persistent period renewal or connected order
capability is approved by this contract; the original owner gates still apply.

## D009 — Atomic synthetic admission store, 10 October 2026

Implement P4.2 as a new broker-neutral SQLite store following
[order-lifecycle-v1](order-lifecycle.md). One transaction owns the synthetic
account snapshot, immutable intent identities, consumed entry attempts, cash,
exposure and planned-loss reservations, incidents and audit sequence. Do not claim
atomicity across the existing separate risk database and in-memory ledger or
destructively migrate them.

Exact request retries are idempotent even after their expected version becomes
stale. Changed reuse of an intent, candidate or client-order identity is a durable
blocking incident. Stale versions and malformed proposals write nothing. Evaluated
rejections consume one of three session attempt slots; attempts and halts are never
refunded or reset. Only the synthetic, flat-account, USD long-entry subset exists.
No writer, broker call, fill, cancellation, automatic expiry release or connected
environment is introduced. See the [admission contract](order-admission.md).

## D010 — Fenced synthetic submission boundary, 10 October 2026

Implement P4.3 in the version-2 order database as a single durable writer event
sequence and submission projection. A claim increments a fencing epoch. Every
marker and result must match the durable owner and epoch; clean explicit recovery
releases ownership for a higher epoch, while an in-flight marker becomes `unknown`
and remains blocked. Do not use lease expiry or automatic takeover.

Commit the immutable operation ID and synthetic command before the adapter call.
Once marked, exact retry returns the stored state and never calls the adapter.
Lost acknowledgement or failure to commit the result remains unresolved and keeps
all account resources. Expired never-dispatched authority is the only P4.3 release:
record cancellation and release atomically without refunding the attempt. Broker
rejection, acknowledgement and terminal labels do not establish reconciled cash,
position, executions, fees or settlement.

The adapter is deterministic and in-process with no connected endpoint. Existing
version-1 admission stores remain readable, but require a separate explicit
migration before writer use. P4.4 owns external reconciliation and resolution.
See the [writer contract](order-writer.md).

## D011 — Cumulative synthetic reconciliation, 10 October 2026

Implement P4.4 in the version-3 order database with a durable cumulative inbox,
reconciliation event sequence and projection. Startup recovery and disconnects
always disarm the writer and require complete supplied evidence before a new claim.
An empty order list never resolves a possibly sent submission.

Accept accounting changes only when the order, stable execution IDs, commission
IDs/revisions, qualified position, USD cash and settlement declaration agree. Commit
cash, position, remaining reservations, loss latches, order projection, writer state
and audit in one transaction. Exact snapshots are idempotent; changed stable IDs,
overfills, unknown external activity and terminal-state regression are durable
incidents. Attempts and halts are never cleared.

This is a synthetic USD long-entry boundary with required empty settlement evidence,
not a connected broker adapter. P4.5 owns cancellation, position-reducing sells,
sell-proceeds settlement and protection incidents. Existing version-1/2 databases
need an explicit migration; no automatic repair or live capability is introduced.
See [synthetic reconciliation](order-reconciliation.md).

## D012 — Public broker capability research, 10 October 2026

Retain IBKR as the first integration candidate and Saxo as the alternative from
the earlier feasibility research. The [dated matrix](broker-capability-matrix.md)
delivers P2.1 and records P2.2's documented surfaces and unresolved account facts.
This is research continuation, not the P2.5 owner selection or a verified paper
path. Keep P2.2 in progress and proceed to conditional P2.4 cost screening, now
delivered under D013.

A current-day Gateway execution query cannot prove recovery across midnight.
Broker execution corrections and fee finality need explicit reviewed mappings
before connected reconciliation; synthetic acceptance does not qualify them.
Obtain exact entity/permissions, cash/settlement, data rights and paper-operation
evidence through the matrix's G01–G06 closure record. No account, funding, paid
service, connected submission, risk-policy change or live activation is approved.

## D013 — Conditional cost feasibility, 10 October 2026

Accept the [dated P2.4 cost model](cost-feasibility.md) as a conditional public
screen, not an account tariff or broker/feed selection. Preserve the £3 all-in
trade-loss cap and £10 recurring monthly ceiling. Unknown spread, slippage, route,
API data, existing-subscription and VPS-allocation costs never become zero.

One-share IBKR tiered and Saxo prefunded-USD cases may have trade-risk headroom
under explicit sensitivity assumptions. Saxo Classic automatic conversion can
consume most or all of that headroom. No complete recurring stack currently passes
on evidenced costs: IBKR's $4.50 direct-network route may fit but account/API rights
and VPS allocation are open, its $14.50 bundle route exceeds £10 in the screened
FX range, Massive real-time NBBO is far above it, and Saxo data pricing is unknown.
Keep P2.2/P2.3 and G01–G06 open, then require Derek's P2.5
proceed/revise/stop choice. Do not purchase access, manufacture commission waivers,
change the frozen hypothesis or weaken a financial limit.
