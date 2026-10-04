"""SQLite-backed offline risk observations. No order authority or halt reset API."""
from contextlib import contextmanager
from dataclasses import asdict
from datetime import timedelta
import json
import os
from pathlib import Path
import sqlite3
from zoneinfo import ZoneInfo

from .data import decode
from .ledger import utc
from .risk import Mark, Policy, assess

APP_ID = 0x54524433


def pack(value):
    return json.dumps(value, default=str, sort_keys=True, separators=(",", ":"))


def periods(at):
    local = utc(at).astimezone(ZoneInfo("America/New_York")).date()
    return local.isoformat(), (local - timedelta(days=local.weekday())).isoformat()


def policy_payload():
    return {key: str(value) for key, value in asdict(Policy()).items()}


def mark_payload(mark):
    return {key: str(value) for key, value in asdict(mark).items()}


def parse_mark(value):
    if not isinstance(value, dict) or set(value) != {"equity", "deposits", "withdrawals"}:
        raise ValueError("Mark requires equity and cumulative deposits/withdrawals")
    return Mark(**value)


def from_ledger(identity, value):
    """Use net account equity including cash and FX, not trade-only P&L."""
    if not isinstance(value, dict) or value.get("mode") != "offline_accounting_only":
        raise ValueError("Expected an offline ledger valuation")
    mark = Mark(value["equity_gbp"], value["deposits_gbp"], value["withdrawals_gbp"])
    return {"id": identity, "at": utc(value["as_of"]).isoformat(), "mark": mark_payload(mark)}


@contextmanager
def database(path, write=False):
    # rw/ro never silently create a missing database after a restart or typo.
    uri = Path(path).resolve().as_uri() + ("?mode=rw" if write else "?mode=ro")
    connection = sqlite3.connect(uri, uri=True, timeout=3, isolation_level=None)
    try:
        connection.execute("PRAGMA synchronous=FULL")
        if connection.execute("PRAGMA application_id").fetchone()[0] != APP_ID:
            raise ValueError("Not a Trad3r risk database")
        if connection.execute("PRAGMA user_version").fetchone()[0] != 1:
            raise ValueError("Unsupported risk database version")
        if connection.execute("PRAGMA quick_check").fetchone()[0] != "ok":
            raise ValueError("Risk database integrity check failed")
        connection.execute("BEGIN IMMEDIATE" if write else "BEGIN")
        yield connection
        connection.commit()
    except BaseException:
        connection.rollback()
        raise
    finally:
        connection.close()


def read_state(connection):
    row = connection.execute("SELECT payload FROM state WHERE id=1").fetchone()
    if row is None:
        raise ValueError("Risk state missing; explicit recovery required")
    state = decode(row[0])
    if not isinstance(state, dict) or set(state) != {
        "version", "policy", "session", "week", "session_start", "week_start",
        "latest", "latest_at", "halt_reasons"
    }:
        raise ValueError("Invalid stored risk state")
    if state["policy"] != policy_payload():
        raise ValueError("Stored risk policy differs; explicit migration required")
    if type(state["version"]) is not int or state["version"] < 0:
        raise ValueError("Invalid state version")
    current = parse_mark(state["latest"])
    session, week = parse_mark(state["session_start"]), parse_mark(state["week_start"])
    if session != Mark(Policy().initial_capital) or week != session:
        raise ValueError("Unexpected baseline change; resets are not implemented")
    if not isinstance(state["halt_reasons"], list):
        raise ValueError("Invalid halt state")
    assess(current, session, week, tuple(state["halt_reasons"]))
    periods(state["latest_at"])
    count = connection.execute("SELECT count(*) FROM observations").fetchone()[0]
    if count != state["version"]:
        raise ValueError("Risk audit/state version mismatch")
    if count:
        row = connection.execute("SELECT payload FROM observations WHERE version=?",
                                 (state["version"],)).fetchone()
        if row is None or pack(decode(row[0])["result"]) != pack(report(state)):
            raise ValueError("Risk audit/state contents mismatch")
    return state


def report(state):
    current = parse_mark(state["latest"])
    assessment = assess(current, parse_mark(state["session_start"]),
                        parse_mark(state["week_start"]), tuple(state["halt_reasons"]))
    changed_period = periods(state["latest_at"]) != (state["session"], state["week"])
    blocked = list(assessment.halt_reasons)
    if changed_period:
        blocked.append("period_review_required")
    return {
        "mode": "offline_risk_observations_only", "version": state["version"],
        "as_of": state["latest_at"], "mark": state["latest"],
        "baseline_session": state["session"], "baseline_week": state["week"],
        "assessment": asdict(assessment), "blocked": bool(blocked),
        "blocked_reasons": sorted(blocked), "live_trading_enabled": False,
    }


def initialize(path, at):
    at = utc(at).isoformat()
    session, week = periods(at)
    initial = mark_payload(Mark(Policy().initial_capital))
    state = dict(version=0, policy=policy_payload(), session=session, week=week,
                 session_start=initial, week_start=initial, latest=initial,
                 latest_at=at, halt_reasons=[])
    path = Path(path)
    descriptor = os.open(path, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
    os.close(descriptor)
    try:
        with sqlite3.connect(path) as connection:
            connection.execute("PRAGMA synchronous=FULL")
            connection.execute(f"PRAGMA application_id={APP_ID}")
            connection.execute("PRAGMA user_version=1")
            connection.execute("CREATE TABLE state (id INTEGER PRIMARY KEY CHECK(id=1), payload TEXT NOT NULL)")
            connection.execute("CREATE TABLE observations (id TEXT PRIMARY KEY, version INTEGER UNIQUE NOT NULL, payload TEXT NOT NULL)")
            connection.execute("INSERT INTO state VALUES (1, ?)", (pack(state),))
        # sqlite context management commits but does not close the connection.
        connection.close()
    except BaseException:
        if 'connection' in locals():
            connection.close()
        path.unlink(missing_ok=True)
        raise
    return report(state)


def status(path):
    with database(path) as connection:
        return report(read_state(connection))


def history(path):
    with database(path) as connection:
        read_state(connection)
        return [decode(row[0]) for row in connection.execute(
            "SELECT payload FROM observations ORDER BY version")]


def record(path, observation, expected_version):
    if type(expected_version) is not int or expected_version < 0:
        raise ValueError("Expected version must be a nonnegative integer")
    if not isinstance(observation, dict) or set(observation) != {"id", "at", "mark"}:
        raise ValueError("Observation requires id, at and mark")
    identity = observation["id"]
    if not isinstance(identity, str) or not identity or len(identity) > 128:
        raise ValueError("Invalid observation id")
    at = utc(observation["at"])
    current = parse_mark(observation["mark"])
    with database(path, write=True) as connection:
        state = read_state(connection)
        if state["version"] != expected_version:
            raise ValueError("State version changed; read status before retrying")
        if at <= utc(state["latest_at"]):
            raise ValueError("Observation must be newer than the stored mark")
        if connection.execute("SELECT 1 FROM observations WHERE id=?", (identity,)).fetchone():
            raise ValueError("Duplicate observation id")
        previous = parse_mark(state["latest"])
        if current.deposits < previous.deposits or current.withdrawals < previous.withdrawals:
            raise ValueError("Cumulative external flows went backwards")
        assessment = assess(current, parse_mark(state["session_start"]),
                            parse_mark(state["week_start"]), tuple(state["halt_reasons"]))
        state.update(version=expected_version + 1, latest=mark_payload(current),
                     latest_at=at.isoformat(), halt_reasons=list(assessment.halt_reasons))
        result = report(state)
        entry = dict(id=identity, at=at.isoformat(), mark=mark_payload(current), result=result)
        connection.execute("INSERT INTO observations VALUES (?, ?, ?)",
                           (identity, state["version"], pack(entry)))
        connection.execute("UPDATE state SET payload=? WHERE id=1", (pack(state),))
        return result
