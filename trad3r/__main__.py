"""Small offline CLI. No account credentials, network or order endpoints."""
import argparse
import hashlib
import json
import sys
from dataclasses import asdict
from pathlib import Path
from zipfile import BadZipFile

from .data import decode, load_sample
from .risk import Mark, assess


def main(argv=None):
    parser = argparse.ArgumentParser(description="Trad3r offline research foundation")
    commands = parser.add_subparsers(dest="command", required=True)
    for name in ("validate", "replay"):
        sub = commands.add_parser(name)
        sub.add_argument("archive", type=Path)
        if name == "replay":
            sub.add_argument("--journal", type=Path, required=True, help="New output file; existing files are not overwritten")
    risk = commands.add_parser("risk-check", help="Assess explicit GBP snapshots; no persistent controller")
    risk.add_argument("snapshots", type=Path)
    args = parser.parse_args(argv)
    try:
        if args.command == "risk-check":
            payload = decode(args.snapshots.read_bytes())
            result = assess(Mark(**payload["current"]), Mark(**payload["session_start"]),
                            Mark(**payload["week_start"]), tuple(payload.get("latched", [])))
            print(json.dumps(asdict(result), default=str, sort_keys=True))
            return 0
        bars, summary = load_sample(args.archive)
        if args.command == "replay":
            digest = hashlib.sha256()
            # Validate input completely before creating an output. Exclusive create
            # protects existing results and input files from accidental overwrite.
            with args.journal.open("xb") as stream:
                for bar in bars:
                    line = (json.dumps(bar.event(), sort_keys=True, separators=(",", ":")) + "\n").encode()
                    stream.write(line)
                    digest.update(line)
            summary["journal_sha256"] = digest.hexdigest()
        print(json.dumps(summary, sort_keys=True, indent=2))
        return 0
    except (OSError, ValueError, KeyError, TypeError, ArithmeticError, BadZipFile) as error:
        print("Input/output error: " + str(error), file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
