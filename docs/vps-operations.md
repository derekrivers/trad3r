# Offline jobs and eventual VPS operation

`run-job` operates one isolated, registered historical experiment. It does not
connect to a broker or feed, place orders, continue a paper account, or reset a risk
store. There is no daily timer. A scheduled daily paper process needs a different,
reviewed account lifecycle and fresh data; historical reruns are not that process.

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

`deploy/trad3r-backtest@.service` is a template for a future Linux VPS with systemd,
Python 3.11+ and timezone data. It is not installed or deployed by this repository.
Before deployment, verify the host OS, resources, local storage and backup access.

Prepare a dedicated unprivileged `trad3r` service account. Install a reviewed,
CI-passing revision in `/opt/trad3r`, with its virtual environment at
`/opt/trad3r/.venv`. Root should own the code/environment; the service account should
only be able to read them. Install dependencies before starting the offline service.
Keep one immutable installation per active code fingerprint; do not update code
under a running or registered job.

Stage the five-file job location at `/var/lib/trad3r/jobs/JOB_ID` (initially just the
three inputs), owned by `trad3r`, mode 0700. Use a simple lowercase alphanumeric,
underscore or hyphen identifier. Register the inputs with the installed Python/code
before outcomes. Keep source/assumptions/registration private and unchanged.

After copying the template to `/etc/systemd/system/`, an administrator can run:

```sh
sudo systemd-analyze verify /etc/systemd/system/trad3r-backtest@.service
sudo systemctl daemon-reload
sudo systemctl start trad3r-backtest@JOB_ID.service
sudo systemctl status trad3r-backtest@JOB_ID.service
sudo journalctl -u trad3r-backtest@JOB_ID.service --no-pager
sudo -u trad3r /opt/trad3r/.venv/bin/python -m trad3r inspect-experiment /var/lib/trad3r/jobs/JOB_ID/result.zip
```

Replace `JOB_ID` with the staged directory name. Success exits the oneshot unit;
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

## Backups and upgrades

Stop the unit before copying its SQLite database and input/output files. Retain
registration, source and result hashes plus the reviewed commit. Restore to a
separate private directory, then run `run-job` to verify an already-completed job;
do not merge two job directories. Keep licensed data out of git and public logs.

For a new code revision, create a new registered engineering job with an explicit
purpose. Preserve old results and registrations; an upgrade cannot relabel them
as unseen validation data. An incomplete old registration needs its exact original
code to resume computation. Completed bundles can be inspected using compatible
newer code without rerunning them.

VPS credentials/access have not been supplied. No host is configured and no job is
scheduled. Forward paper readiness is tracked separately in the roadmap.
