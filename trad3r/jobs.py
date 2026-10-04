"""Single-machine recoverable jobs for isolated engineering experiments only."""
import os
from pathlib import Path
import re
import sqlite3

from . import experiments as experiment
from .data import decode

APPLICATION_ID = 0x54334A31
SCHEMA = "CREATE TABLE job (id INTEGER PRIMARY KEY CHECK (id = 1), registration_sha TEXT NOT NULL, bundle_sha TEXT)"


def _identity(connection, registration_sha):
    app_id = connection.execute("PRAGMA application_id").fetchone()[0]
    version = connection.execute("PRAGMA user_version").fetchone()[0]
    objects = connection.execute("SELECT type, name, sql FROM sqlite_master ORDER BY name").fetchall()
    if app_id == 0 and version == 0 and not objects:
        connection.execute(SCHEMA)
        connection.execute(f"PRAGMA application_id = {APPLICATION_ID}")
        connection.execute("PRAGMA user_version = 1")
        connection.execute("INSERT INTO job VALUES (1, ?, NULL)", (registration_sha,))
    elif (app_id != APPLICATION_ID or version != 1
          or objects != [("table", "job", SCHEMA)]):
        raise ValueError("Unknown job database; preserve it for investigation")
    rows = connection.execute("SELECT id, registration_sha, bundle_sha FROM job").fetchall()
    if (len(rows) != 1 or rows[0][0] != 1 or rows[0][1] != registration_sha
            or rows[0][2] is not None and not re.fullmatch(r"[0-9a-f]{64}", rows[0][2])):
        raise ValueError("Job identity changed or state is inconsistent")
    return rows[0][2]


def _durable_result(path):
    # Publish is exclusive and atomic. Flush file and directory before recording
    # completion; storage/hardware still determine power-loss durability.
    with path.open("rb") as stream:
        os.fsync(stream.fileno())
    if os.name == "posix":
        directory = os.open(path.parent, os.O_RDONLY)
        try:
            os.fsync(directory)
        finally:
            os.close(directory)


def run_job(directory):
    """Run once, verify a completed job, or recover its already-published bundle.

    SQLite's write lock excludes concurrent runners on a local filesystem. This
    is not an order queue, account restart, scheduler or distributed lock.
    """
    directory = Path(directory)
    if not directory.is_dir():
        raise ValueError("Job directory must already exist with its three input files")
    paths = {name: directory/name for name in
             ("registration.json", "assumptions.json", "source.zip", "result.zip", "job.sqlite")}
    if any(path.is_symlink() for path in paths.values()):
        raise ValueError("Job files must not be symbolic links")
    registration_raw = experiment._read(paths["registration.json"])
    record = decode(registration_raw)
    experiment._validate_registration(record)
    registration_sha = experiment.digest(registration_raw)
    for name, key, limit in (("source.zip", "source_sha256", 50 * 1024 * 1024),
                             ("assumptions.json", "assumptions_sha256", 64 * 1024)):
        if experiment.digest(experiment._read(paths[name], limit)) != record[key]:
            raise ValueError("Job input differs from registration")
    try:
        with paths["job.sqlite"].open("xb"):
            pass
        paths["job.sqlite"].chmod(0o600)
    except FileExistsError:
        pass
    connection = sqlite3.connect(paths["job.sqlite"], timeout=0, isolation_level=None)
    try:
        connection.execute("PRAGMA synchronous = FULL")
        connection.execute("BEGIN IMMEDIATE")
        _identity(connection, registration_sha)
        # Retain the first registered identity even if computation is interrupted.
        connection.commit()
        connection.execute("BEGIN IMMEDIATE")
        previous_sha = _identity(connection, registration_sha)
        output = paths["result.zip"]
        if output.exists():
            summary = experiment.inspect_experiment(output)
            outcome = "already_complete" if previous_sha else "recovered_published_result"
        else:
            if previous_sha:
                raise ValueError("Completed job result is missing; restore the original, do not rerun")
            summary = experiment.run_experiment(paths["registration.json"], paths["source.zip"],
                                                 paths["assumptions.json"], output)
            outcome = "completed"
        if (summary["registration_sha256"] != registration_sha
                or previous_sha and summary["bundle_sha256"] != previous_sha):
            raise ValueError("Published result differs from the pinned job identity")
        _durable_result(output)
        connection.execute("UPDATE job SET bundle_sha = ? WHERE id = 1", (summary["bundle_sha256"],))
        connection.commit()
        return dict(mode="offline_engineering_job", outcome=outcome,
                    experiment_id=record["experiment_id"], registration_sha256=registration_sha,
                    bundle_sha256=summary["bundle_sha256"], output=str(output),
                    reconciliation=summary["reconciliation"], live_trading_enabled=False)
    finally:
        if connection.in_transaction:
            connection.rollback()
        connection.close()
