# ATLAS synthetic offline deployment — 10 October 2026

The first synthetic Phase 1 milestone is deployed and verified. This is a manually
invoked offline research service, not a connected paper application. No historical
result has been reproduced because the private inputs have not been transferred.
[Plan adoption PR #24](https://github.com/derekrivers/trad3r/pull/24) merged as
`413075d227a407b4be7a2b372ca77a7edb0c3b14`; see the separate
[VPS development baseline](vps-baseline-2026-10-10.md).

## Installed identity and boundaries

- Pinned runtime revision: `ea44cc8ec78703cc3310107e65cfc80739adb46a`, the existing
  reviewed PR #23 build with [passing CI](https://github.com/derekrivers/trad3r/actions/runs/37234109481).
  Documentation adoption does not alter its Python fingerprint:
  `9ecd1a50bdd305c0ed7195cfb999cd9fc4e47d40a36598b40b7ac0c844d88e9a`.
- Source archive extracted to `/opt/trad3r/releases/ea44cc8ec78703cc3310107e65cfc80739adb46a`;
  its own Python 3.12.3 venv contains a regular, non-editable install. Both source
  and environment are root-owned and unwritable by the service account. The
  development checkout/venv remains separate. Source and installed package
  fingerprints match. No third-party Linux runtime dependencies are needed.
- System account `trad3r`, group `trad3r`, shell `/usr/sbin/nologin`; no login/password
  or brokerage credentials. Parent data/job directories are root-owned, mode 0750.
- Job `/var/lib/trad3r/jobs/synthetic-vps-20261010`, owned by `trad3r`, mode 0700.
  Root-owned inputs are mode 0440 with group read access and individually mounted
  read-only by the instance drop-in. Job outputs are private to the service user.
- Installed repository service template plus an instance drop-in pinning the release.
  No mutable current-release symlink, timer, boot enablement or automatic restart.
  An unstaged instance has no configured runtime and must be provisioned explicitly.

The fixture reuses the reviewed `test_preparation.sample` and `assumptions` helpers:
synthetic symbol AAA, two sessions (8–9 September 2026), invented bars and FX.
The API fetcher is mocked; no market-data request or download credential was used.
Registration preceded execution and binds the installed code fingerprint.

## Host acceptance evidence

| Check | Observed evidence |
| --- | --- |
| Identity and privileges | Unprivileged UID; NoNewPrivs=1; zero effective capabilities |
| Effective network isolation | Loopback-only namespace; IPv4 and IPv6 documentation-address connects fail with ENETUNREACH |
| Write boundaries | Code, venv configuration and all three input files reject writable opens; a service-user-writable file outside the job also rejects them inside the sandbox |
| Permitted writes | Exclusive synthetic file can be written/read/removed within the job |
| Temporary isolation | Host /tmp marker is visible outside and hidden inside the service |
| Resource controls | Actual cgroup reports memory.max=1073741824 and pids.max=32; unit reports 30-minute start timeout and Restart=no |
| Initial execution | `completed`, reconciliation `verified`, service exit 0 |
| Repeat execution | `already_complete`; same registration and result identity |
| Separate bundle inspection | Installed CLI `inspect-experiment` succeeds |
| Final operating configuration | Temporary probe drop-in removed; another explicit start returns `already_complete`; inactive, Result=success, exit 0 |

All **16 acceptance-probe checks** passed. The probe is retained at
[deploy/probe-offline-sandbox.py](../deploy/probe-offline-sandbox.py); it must be run
inside the service with the documented host controls. It tests denied opens without
writing to protected files. The temporary writable file and /tmp marker were
removed after evidence capture. Installed release files were not changed.

`systemd-analyze verify` accepted the Trad3r instance. It also emitted an unrelated
existing `Enviroment` spelling warning in a different host service's drop-in;
that service was not edited. The synthetic first run consumed 3.762 CPU seconds.
Peak memory was not retained by systemd after the cgroup exited, so no measured
peak-memory claim is made. Limits were verified in the running cgroup and retained;
OOM/time-limit exhaustion was not injected into the host.

## Recovery and local restore

Ran the existing eight `test_jobs` cases with the **installed package**, as the
unprivileged user inside a separate instance of the same network-disabled sandbox.
Working directory `/tmp`, PYTHONPATH contains only the pinned release's test folder.
All eight passed in 21.996 seconds, including real worker termination before
publication, competing-runner rejection, abrupt exit after publication, adoption
without recomputation, changed input/registration rejection, missing/modified
results, symlink inputs and corrupt/unknown SQLite state. These exercise offline
job recovery, not broker reconciliation or a real power-loss event.

With the job inactive, held its SQLite BEGIN IMMEDIATE lock, required DELETE
journal mode, and copied the five files to a new private backup directory. No
writer can commit while the copy lock is held. Recorded each size/hash plus code
revision/fingerprint in `inventory.json`. Restored into a separate new directory,
verified all five hashes and invoked the installed `run-job` CLI: `already_complete`
with the same result hash. The restore check ran as the administrator outside the
service; service-user execution was separately verified above. Original job state
and result were preserved. Backup and restore directories are root-private (0700).

| Private retained artifact | Location |
| --- | --- |
| Unit logs, effective config, probe, inspection, recovery log and restore report | `/var/lib/trad3r/evidence/20261010/` |
| One-time backup/restore drill source | `/var/lib/trad3r/evidence/20261010/backup-restore.py` |
| Five-file backup and inventory | `/var/lib/trad3r/backups/synthetic-vps-20261010/20261010/` |
| Separate verified restoration | `/var/lib/trad3r/restores/synthetic-vps-20261010-20261010/` |

## Retained identities

| Artifact | SHA-256 |
| --- | --- |
| Synthetic source | `66aebd2191159bd947b9afc4066e18343df4a17551b7edf0f729a899de91b2d3` |
| Registration | `24ea849f40d1a3018362761e9c07458712b71312dd9b0dcd119289792f641815` |
| Result bundle | `cdb695a08980c14ca9ff6557725245d69be59ddf52fedf8b2a1c83628853d44a` |
| Service/probe log | `f2f98e07af42ccfcc4c8e112fcf975c41a6e56e29fcdde51884b8feed45286e9` |
| Installed recovery log | `4a1676c8d30f608fba1e95bf3cdfa408b9383f35298bc03770dde9f2b0a831a1` |
| Restore report | `ad659c7f1de7c01656b809bc950e2860e8b7e97d1bd08dfbbcd76430db9333cb` |
| Backup inventory | `68e6c755859f319544ecfd86338aaf9285439f7d4d5e075e5b40ad8a5d3b8555` |

## Storage and remaining limits

At verification: filesystem 73% used, approximately 9.7 GiB available; Trad3r runtime
17 MiB and initial data/evidence/backups about 248 KiB. Whole-host journals occupied
3.6 GiB; these are shared ATLAS logs, not Trad3r's footprint. No global log vacuum,
retention change or other-workload modification was performed.

Retain the initial backup, matching release, registration and all failure/recovery
evidence. No automatic pruning is enabled. Check disk and logs before each new
explicit job and backup; suspend new research if free space falls below 2 GiB or
usage reaches 80%, then review rather than deleting account/result evidence.
These are operational disk thresholds, not changes to financial limits. The
[runbook](vps-operations.md) gives the inspection commands. No continuous monitor
or notification route is claimed.

P1.6 remains **in progress**: local inventory/retention and restore are exercised,
but off-host destination/access, recurring backup operations and alert delivery
are unresolved. Local copies do not protect against host loss. P1's full exit gate
is not claimed. Private historical inputs and design v2 also remain missing.
No trading, paid service, strategy tuning, model calls or financial-policy changes
were introduced.
