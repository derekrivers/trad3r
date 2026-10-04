"""Small offline CLI. No account credentials, network or order endpoints."""
import argparse
import hashlib
import json
import sys
import sqlite3
from dataclasses import asdict
from pathlib import Path
from zipfile import BadZipFile

from .data import decode, load_sample, parse_bar
from .risk import Mark, assess
from .ledger import Ledger, replay_ledger
from .admission import check_entry
from . import risk_store
from .simulation import simulate, simulate_series
from .batches import completed_batches
from .features import FEATURE_SCHEMA, feature_snapshots
from .strategy import opening_range_signals
from .research import audit_sample


def main(argv=None):
    parser = argparse.ArgumentParser(description="Trad3r offline research foundation")
    commands = parser.add_subparsers(dest="command", required=True)
    audit = commands.add_parser("research-audit", help="Read-only bar inventory and unresolved research gates")
    audit.add_argument("archive", type=Path)
    audit.add_argument("--start", required=True, help="Inclusive first date, YYYY-MM-DD")
    audit.add_argument("--end", required=True, help="Inclusive last date, YYYY-MM-DD")
    for name in ("validate", "replay", "features"):
        sub = commands.add_parser(name)
        sub.add_argument("archive", type=Path)
        sub.add_argument("--require-complete", action="store_true", help="Reject missing scheduled minute bars")
        if name != "validate":
            sub.add_argument("--journal", type=Path, required=True, help="New output file; existing files are not overwritten")
        if name == "replay":
            sub.add_argument("--batches", action="store_true", help="Emit atomic completed-bar batches for all declared symbols")
    risk = commands.add_parser("risk-check", help="Assess explicit GBP snapshots; no persistent controller")
    risk.add_argument("snapshots", type=Path)
    ledger = commands.add_parser("ledger", help="Account for supplied offline events; no generated fills")
    ledger.add_argument("events", type=Path)
    entry = commands.add_parser("entry-check", help="Offline entry diagnostic; no order reservation")
    entry.add_argument("database", type=Path)
    entry.add_argument("events", type=Path)
    entry.add_argument("proposal", type=Path)
    entry.add_argument("--at", required=True)
    entry.add_argument("--attempts", type=int, required=True)
    signals = commands.add_parser("strategy-signals", help="Frozen experimental opening-range candidates")
    signals.add_argument("archive", type=Path)
    signals.add_argument("--symbol", required=True)
    signals.add_argument("--session", required=True)
    for name in ("simulate", "simulate-series", "baseline-simulate"):
        simulation = commands.add_parser(name, help="Offline execution scenarios; no validated performance")
        simulation.add_argument("scenario", type=Path)
        simulation.add_argument("--archive", type=Path, help="Use licensed archive bars instead of inline synthetic bars")
    for command in ("risk-init", "risk-status", "risk-history", "risk-record"):
        sub = commands.add_parser(command, help="Persistent offline risk observations; no halt resets")
        sub.add_argument("database", type=Path)
        if command == "risk-init":
            sub.add_argument("--at", required=True, help="Initial funding timestamp in UTC")
        if command == "risk-record":
            sub.add_argument("observation", type=Path)
            sub.add_argument("--expected-version", type=int, required=True)
            sub.add_argument("--ledger-report", action="store_true", help="Read an offline ledger valuation")
            sub.add_argument("--event-id", help="Required when importing a ledger valuation")
    args = parser.parse_args(argv)
    try:
        if args.command == "research-audit":
            result = audit_sample(args.archive, args.start, args.end)
            print(json.dumps(result, default=str, sort_keys=True, indent=2))
            return 0
        if args.command == "strategy-signals":
            bars, source = load_sample(args.archive)
            if not source["coverage"]["complete"]:
                raise ValueError("Strategy archive must have complete declared coverage")
            selected = [b for b in bars if b.symbol == args.symbol and b.session == args.session]
            result = opening_range_signals(selected, args.symbol)
            result.update(source_sha256=source["source_sha256"], calendar_id=source["calendar_id"])
            print(json.dumps(result, default=str, sort_keys=True, indent=2))
            return 0
        if args.command in ("simulate", "simulate-series", "baseline-simulate"):
            scenario_bytes = args.scenario.read_bytes()
            payload = decode(scenario_bytes)
            scenarios = payload["sessions"] if args.command == "simulate-series" else [payload]
            if not isinstance(scenarios, list) or not scenarios:
                raise ValueError("Supply a nonempty session array")
            source_sha = None
            if args.archive:
                available, source = load_sample(args.archive)
                source_sha = source["source_sha256"]
                if args.command == "baseline-simulate" and not source["coverage"]["complete"]:
                    raise ValueError("Strategy archive must have complete declared coverage")
            sessions = []
            for scenario in scenarios:
                if args.archive:
                    if "bars" in scenario:
                        raise ValueError("Use either an archive or inline bars, not both")
                    bars = [b for b in available if b.symbol == scenario["symbol"] and b.session == scenario["session"]]
                else:
                    bars = [parse_bar(row, scenario["symbol"]) for row in scenario["bars"]]
                if args.command == "baseline-simulate":
                    if "signals" in scenario:
                        raise ValueError("Omit supplied signals for the frozen baseline hypothesis")
                    generated = opening_range_signals(bars, scenario["symbol"])
                    scenario = dict(scenario, signals=generated["signals"])
                sessions.append((bars, scenario))
            result = simulate_series(sessions) if args.command == "simulate-series" else simulate(*sessions[0])
            if args.command == "baseline-simulate":
                result.update(strategy_id=generated["strategy_id"], feature_schema=generated["feature_schema"],
                              research_status="engineering_scenario_only", generated_signals=generated["signals"])
            result.update(scenario_sha256=hashlib.sha256(scenario_bytes).hexdigest(), source_sha256=source_sha)
            print(json.dumps(result, default=str, sort_keys=True, indent=2))
            return 0
        if args.command == "entry-check":
            book = Ledger()
            events = decode(args.events.read_bytes())
            if not isinstance(events, list):
                raise ValueError("Ledger input must be a JSON event array")
            for event in events:
                book.apply(event)
            result = check_entry(book, risk_store.status(args.database),
                                 decode(args.proposal.read_bytes()), args.at, args.attempts)
            print(json.dumps(result, default=str, sort_keys=True, indent=2))
            return 0
        if args.command in ("risk-init", "risk-status", "risk-history", "risk-record"):
            if args.command == "risk-init":
                result = risk_store.initialize(args.database, args.at)
            elif args.command == "risk-record":
                observation = decode(args.observation.read_bytes())
                if args.ledger_report:
                    if not args.event_id:
                        raise ValueError("--ledger-report requires --event-id")
                    observation = risk_store.from_ledger(args.event_id, observation)
                elif args.event_id:
                    raise ValueError("--event-id requires --ledger-report")
                result = risk_store.record(args.database, observation, args.expected_version)
            elif args.command == "risk-history":
                result = risk_store.history(args.database)
            else:
                result = risk_store.status(args.database)
            print(json.dumps(result, default=str, sort_keys=True, indent=2))
            return 0
        if args.command == "ledger":
            events = decode(args.events.read_bytes())
            if not isinstance(events, list):
                raise ValueError("Ledger input must be a JSON event array")
            print(json.dumps(replay_ledger(events), default=str, sort_keys=True, indent=2))
            return 0
        if args.command == "risk-check":
            payload = decode(args.snapshots.read_bytes())
            result = assess(Mark(**payload["current"]), Mark(**payload["session_start"]),
                            Mark(**payload["week_start"]), tuple(payload.get("latched", [])))
            print(json.dumps(asdict(result), default=str, sort_keys=True))
            return 0
        bars, summary = load_sample(args.archive)
        if (args.require_complete or args.command == "features") and not summary["coverage"]["complete"]:
            raise ValueError("Archive is missing scheduled minute bars")
        if args.command in ("replay", "features"):
            if args.command == "features":
                events = feature_snapshots(bars, summary["symbols"])
                summary.update(mode="offline_features_only", feature_schema=FEATURE_SCHEMA,
                               journal_format=FEATURE_SCHEMA)
            else:
                frames = completed_batches(bars, summary["symbols"]) if args.batches else bars
                events = [frame.event() for frame in frames]
                summary["journal_format"] = "completed_batches_v1" if args.batches else "completed_bars_v1"
            digest = hashlib.sha256()
            # Validate input completely before creating an output. Exclusive create
            # protects existing results and input files from accidental overwrite.
            with args.journal.open("xb") as stream:
                for event in events:
                    line = (json.dumps(event, default=str, sort_keys=True, separators=(",", ":")) + "\n").encode()
                    stream.write(line)
                    digest.update(line)
            summary["journal_sha256"] = digest.hexdigest()
            summary["journal_events"] = len(events)
        print(json.dumps(summary, sort_keys=True, indent=2))
        return 0
    except (OSError, ValueError, KeyError, TypeError, ArithmeticError, BadZipFile, sqlite3.Error) as error:
        print("Input/output error: " + str(error), file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
