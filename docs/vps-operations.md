# Offline jobs and VPS operation

`run-job` operates one isolated, registered historical experiment. It does not
connect to a broker or feed, place orders, continue a paper account, or reset a risk
store. There is no daily timer. A scheduled daily paper process needs a different,
reviewed account lifecycle and fresh data; historical reruns are not that process.

The [10 October ATLAS deployment record](vps-deployment-2026-10-10.md) contains
actual synthetic job, sandbox, recovery and local restore evidence. Only the
explicitly staged synthetic instance is deployed; historical reproduction and
off-host backup remain open. No service timer is installed.

## Prepare and run locally

Create a new private job directory on a local filesystem that supports SQLite
locking and hard links. Do not use a network mount or shared cloud-sync directory.
Place the licensed archive at `source.zip` and the declared cost assumptions at
`assumptions.json`. Register using the exact code installation that will run it:

```sh
mkdir -p runs/job-example
chmod 700 runs/job-example
cp data/combined.zip runs/job-example/source.zip
cp data/assumptions.json runs/job-example/assumptions.json
python -m trad3r register-experiment runs/job-example/source.zip runs/job-example/assumptions.json --id aapl-job-example --symbol AAPL --start 2026-09-04 --end 2026-10-02 --output runs/job-example/registration.json
python -m trad3r run-job runs/job-example
python -m trad3r inspect-experiment runs/job-example/result.zip
python -m trad3r run-job runs/job-example
```

The second job command verifies the retained bundle and returns `already_complete`;
it does not execute the strategy again. Outputs are `result.zip` and coordination
database `job.sqlite`. Keep all five files and the exact code revision together in
your private backup inventory. Inputs must remain unchanged while a job runs. This
single-user workflow is not hardened against a hostile process modifying its files.

## Failure and restart contract

The job pins the registration identity before computation. A SQLite write lock
then excludes other runners through execution, verification and completion commit.
Another runner fails immediately while that lock is held. A terminated process
releases the operating-system lock; no stale PID-file cleanup is needed.

| Observed state | Next invocation |
| --- | --- |
| Registered job, no result | Execute the same isolated experiment |
| Complete result published, completion commit interrupted | Inspect and adopt the matching result without rerunning |
| Completion recorded, exact result present | Inspect and return `already_complete` |
| Completion recorded, result missing or changed | Fail; restore the original backup or investigate |
| Changed registration/input, unknown database, inconsistent state | Fail; preserve evidence |

File and directory contents are flushed before completion is committed on POSIX;
SQLite uses FULL synchronous mode. Hardware and filesystem failures still require
backups. Never delete a job database/result merely to make an error disappear.
Crash recovery tests cover real subprocess termination before publication and an
abrupt process exit after publication. These tests make no broker-order guarantee.

## Linux systemd template

`deploy/trad3r-backtest@.service` is the Linux template for systemd, Python 3.11+
and timezone data. The repository alone does not deploy it; the ATLAS instance
was explicitly installed and verified as recorded above. Before another
deployment, verify the host OS, resources, local storage and backup access.

Prepare a dedicated unprivileged `trad3r` service account. Install each reviewed,
CI-passing revision under `/opt/trad3r/releases/REVIEWED_SHA`, with its own `.venv`
and a regular, non-editable package installation. Root owns code and environment;
the service user only reads them. Install dependencies before the offline start.
Retain the source revision and verify its Python fingerprint against the installed
package from outside the development checkout. Do not update a running/registered
job's release or repoint a shared symlink.

The template's original `/opt/trad3r/.venv` path is overridden **per instance**.
Copy [pinned-release.conf.example](../deploy/pinned-release.conf.example) into
`/etc/systemd/system/trad3r-backtest@JOB_ID.service.d/10-pinned-release.conf` and
replace `REVIEWED_SHA`. This binds execution and individually read-only input
mounts to that job. Unconfigured instances must not be started.

Stage the five-file job location at `/var/lib/trad3r/jobs/JOB_ID` (initially just the
three inputs), owned by `trad3r`, mode 0700. Parent directories are root-owned,
0750, group `trad3r`. Use a simple lowercase alphanumeric, underscore or hyphen
identifier. Register with the matching installed Python/code before outcomes.
Set the three input files to root:trad3r, mode 0440; the instance's ReadOnlyPaths
protects them from modification or unlink inside the sandbox. Outside the sandbox,
a process owning the job directory could replace entries: this remains a trusted
single-user offline workflow, not protection against a malicious host user.

After copying the template to `/etc/systemd/system/`, an administrator can run:

```sh
sudo systemd-analyze verify /etc/systemd/system/trad3r-backtest@JOB_ID.service
sudo systemctl daemon-reload
sudo systemctl start trad3r-backtest@JOB_ID.service
sudo systemctl status trad3r-backtest@JOB_ID.service
sudo journalctl -u trad3r-backtest@JOB_ID.service --no-pager
sudo -u trad3r /opt/trad3r/releases/REVIEWED_SHA/.venv/bin/python -m trad3r inspect-experiment /var/lib/trad3r/jobs/JOB_ID/result.zip
```

Replace `JOB_ID` and `REVIEWED_SHA` with the staged job and pinned revision.
Success exits the oneshot unit;
an inactive unit after successful completion is expected. Check exit status and the
verified bundle. A failed or timed-out unit must be investigated before restart.
Use `systemctl stop` to interrupt computation, then inspect the directory before
starting the same job. Do not weaken its checks to bypass a failure.

The template disables networking, removes capabilities, makes the system read-only
apart from this job directory, uses private temporary storage and runs as nonroot.
The oneshot startup timeout is 30 minutes, with a 1 GiB memory and 32-task limit.
Those are initial operational limits, not measured VPS capacity guarantees; a
resource failure cannot be represented as a successful backtest. There is no
automatic restart or account renewal. Validate effective sandboxing on the actual
host before using it. Template parsing alone does not prove host isolation.

Official configuration references:
[systemd execution sandbox](https://github.com/systemd/systemd/blob/main/man/systemd.exec.xml)
and [oneshot service/timeout semantics](https://github.com/systemd/systemd/blob/main/man/systemd.service.xml).

## Repeat the host sandbox probe

Use [probe-offline-sandbox.py](../deploy/probe-offline-sandbox.py) as a temporary
ExecStartPre in a synthetic instance. Install the probe root-owned and read-only
outside the job. Pass `--job`, `--release`, `--outside-file` and `--host-tmp-marker`
with absolute paths. Before the test, create an empty outside file owned/writable
by `trad3r` and a host /tmp marker. Confirm an ordinary `runuser -u trad3r` process
can open the former writable and see the latter; these positive controls prevent
missing files or normal permissions from being mistaken for effective isolation.

The probe checks actual UID, capabilities, network namespace, IPv4/IPv6 routing,
protected writes, permitted job writes, PrivateTmp and running cgroup memory/task
limits. It creates one exclusive `sandbox-write-probe` in the job and removes it.
A failed check exits nonzero and prevents job execution. Capture the journal and
unit configuration, remove the temporary probe drop-in and its two host controls,
reload systemd, then verify the normal instance again. Never weaken the production
sandbox to accommodate the probe. An untested check is not a pass.

## Backups and upgrades

Stop the unit and ensure it is inactive before backup. Also exclude manual
runners with a SQLite BEGIN IMMEDIATE lock held throughout the five-file copy.
The deployed job uses DELETE journal mode; refuse a raw copy if the mode differs.
Use a SQLite-aware backup procedure for WAL or other database configurations.
Copy source, assumptions, registration, result and job.sqlite into a new private
0700 snapshot. Reject symlink inputs. Never overwrite an existing backup.

Record all five sizes/SHA-256 values, source revision and code fingerprint in an
inventory alongside the snapshot. Retain the matching root-owned release and
effective service configuration. Restore to a separate new private directory,
verify every hash, then run `run-job` with the matching installed Python. A completed
restore must return `already_complete` and the original bundle identity, not a new
computation. Do not merge job directories. Keep inputs/results and logs private.

Retention currently keeps all snapshots and the original deployment evidence;
there is no automatic deletion. Before expanding beyond the synthetic milestone,
choose the owner-approved off-host destination, access boundary, backup frequency
and a capacity-bounded retention policy. Preserve original results and code needed
by incomplete jobs. Local copies alone cannot meet the host-loss requirement.

Before each explicit job/backup, inspect:

```sh
df -h /var/lib/trad3r
du -sh /var/lib/trad3r /opt/trad3r
journalctl --disk-usage
systemctl show trad3r-backtest@JOB_ID.service -p ActiveState -p Result -p ExecMainStatus
journalctl -u trad3r-backtest@JOB_ID.service --no-pager -n 60
```

Pause new research at 80% filesystem use or below 2 GiB free and review capacity.
Do not vacuum shared host logs or remove job/risk evidence as an automatic remedy.
These are on-demand checks; recurring monitoring/alerts remain open. Capture
per-service logs privately because future jobs can contain licensed evidence.

For a new code revision, create a new registered engineering job with an explicit
purpose. Preserve old results and registrations; an upgrade cannot relabel them
as unseen validation data. An incomplete old registration needs its exact original
code to resume computation. Completed bundles can be inspected using compatible
newer code without rerunning them.

For a failed deployment, stop only the affected Trad3r instance and preserve its
job/evidence. Restore its recorded per-instance configuration and matching retained
release, reload systemd, reverify the sandbox and inspect the job before an explicit
restart. Never roll back an account's economic history or replace a registration to
fit different code. This deployment introduced no database schema migration.

ATLAS now has the explicitly started synthetic offline instance. It is inactive
after successful completion; no future run is scheduled. Forward paper readiness
is tracked separately in the roadmap.
