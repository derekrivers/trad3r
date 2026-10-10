# Project status

Updated 10 October 2026. [Master plan](project-plan.md) version 1.0 is canonical
once this adoption PR merges. [Decisions](decisions.md) retain owner gates.
Initial inspected code: `ea44cc8ec78703cc3310107e65cfc80739adb46a`.

## Active package

| Task | Status | Dependency | PR / revision and validation | Remaining limitation / next action |
| --- | --- | --- | --- | --- |
| P0.1 workspace | complete | Existing checkout | Adoption PR; clean main at `ea44cc8`; matching origin and passing hosted CI recorded in [baseline](vps-baseline-2026-10-10.md) | Preserve branch isolation for each increment |
| P0.2 plan adoption | in progress | P0.1 | Adoption PR; exact supplied plan, README/roadmap links, status and decisions | Review and hosted CI before merge |
| P0.3 design v2 | blocked | Owner artifact | D002; scoped filename inventory | Supply location; map actual requirements without inventing text |
| P0.4 VPS baseline | complete | P0.1 | `ea44cc8`; 236 tests passed, no skips; 17 rehearsal checks passed | Service sandbox requires separate verification |
| P0.5 private inventory | complete | P0.1 | [Scoped inventory](vps-baseline-2026-10-10.md); original hashes remain in historical records | Assets absent; hash matching and historical reproduction blocked |
| P1.1 pinned runtime | not started | P0 adoption | Existing service template and reviewed code | Install immutable release and unprivileged account |
| P1.2 stage job | not started | P1.1 | Existing register-experiment CLI | Stage labelled synthetic fixture; register with installed build |
| P1.3 host sandbox | not started | P1.1–2 | Existing template only | Verify effective networking, writes and resource limits |
| P1.4 execute job | not started | P1.3 | Existing run-job/inspect commands | Run and repeat synthetic job; historical run awaits private data |
| P1.5 recovery | not started | P1.4 | Existing subprocess recovery tests passed in VPS suite | Exercise installed build and preserve host evidence |
| P1.6 backups | not started | P1.4 | Existing runbook | Local inventory/restore/retention and disk/log checks; off-host destination awaits owner |

P0 may exit after adoption: missing design/private inputs block only dependent
work. Inventory completion means missing assets are explicitly recorded, not
that their hashes were verified. P1 cannot be declared fully complete without
its host evidence and approved off-host backup path.

## Ordered continuation

1. Finish adoption review/CI/merge; deploy the reviewed offline runtime.
2. Complete the synthetic P1 service, isolation, recovery and local restore package.
3. Locate private inputs and design v2; choose an off-host backup destination.
4. P2.1–P2.5 broker/data feasibility and owner decisions; P4.1 durable order-state
   contract and synthetic execution work can follow independently.
5. P3.1–P3.6 data qualification; P4.2–P4.7 persistent controls; then P5–P10 in the
   canonical dependency order. These new tasks are not started; existing offline
   capabilities retain credit in [roadmap](roadmap.md).

Connected paper submissions, live execution, purchases and changes to financial
policy remain gated. No unattended work or daily service timer is scheduled.
