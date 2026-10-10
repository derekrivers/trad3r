# ATLAS baseline verification — 10 October 2026

Inspected `/root/trad3r` on ATLAS at revision
`ea44cc8ec78703cc3310107e65cfc80739adb46a`. The initial branch was `main`, the
working tree was clean, and fetched `origin/main` matched. The sole remote was
`https://github.com/derekrivers/trad3r.git`. Existing hosted CI passed on that SHA:
[run 37234109481](https://github.com/derekrivers/trad3r/actions/runs/37234109481).
Changes for adoption use a feature branch; no direct main commit is made.

## Actual host verification

Ubuntu 24.04.4 LTS, Python 3.12.3, systemd 255, two CPUs, approximately 3.7 GiB RAM
and 9.8 GiB disk available at inspection. `timedatectl status` reported synchronized
clock and active NTP; host timezone is UTC. No Trad3r systemd units, runtime
installation, service account or staged jobs existed at initial inspection. Other
ATLAS services were running and were not modified.

Created `/root/trad3r/.venv` with `python3 -m venv .venv`, then installed the checkout
with `.venv/bin/python -m pip install -e .`. Linux uses system timezone data; there
are no third-party runtime dependencies on this platform.

- `.venv/bin/python -m unittest discover -s tests -v`: **236 passed, zero skipped**,
  81.607 seconds, exit 0. The earlier supplied snapshot's one skip did not recur:
  this host permits the symbolic-link test.
- `.venv/bin/python -m trad3r rehearse-controls runs/vps-baseline-20261010/controls`:
  **17 checks passed**, exit 0. Retained synthetic risk state and ledger evidence;
  no orders generated and paper/live readiness remains false.
- Full private local evidence: `/root/trad3r/runs/vps-baseline-20261010/`, including
  `tests.log`, `controls.json` and the `controls/` artifacts. These are new VPS
  observations, distinct from the preserved October 4 results.

Evidence SHA-256 values:

| Artifact | SHA-256 |
| --- | --- |
| Shipped Python code fingerprint | `9ecd1a50bdd305c0ed7195cfb999cd9fc4e47d40a36598b40b7ac0c844d88e9a` |
| VPS test log | `c7d065f662c83eb9b1e716390f359c64ddd129ff3aca1cabf9423331bbe557c5` |
| Control rehearsal report | `ccdffa23ed08480b65359f3ae339555e48d6617a9a67b4c5f19bcf92376b1dae` |

## Private-data inventory

Checked the checkout (including ignored data/run paths), `/root/.codex/attachments`,
`/root`, `/home`, `/srv`, `/opt` and `/var/lib` by relevant ZIP, registration,
assumption and design filenames. Excluded cache/git internals. No retained Trad3r
licensed source ZIP, FX export, original registration, original assumptions, result
bundle or full discretionary design v2 was found. This is a scoped inventory, not
proof that no other private location exists. Unrelated ATLAS archives were not
opened or treated as Trad3r evidence. The checked-in research assumptions are an
example, not the original private historical assumptions.

The [historical results](first-engineering-results.md) retain the combined source
hash and all three registration/result hashes. [Original validation](validation.md)
retains the raw-source and replay hashes. The owner confirmed no files have been transferred yet.
Matching these is **blocked: files absent**.
Do not replace them with synthetic data or claim historical reproduction. Once the
owner identifies the files, hash them, compare every retained identity and inspect
the bundles before planning a new registered reproduction.

## Subsequent attachment

The owner then supplied `trad3r-data-downloader.zip` (SHA-256
`449643fa7257c1f612a44c7edf14f089244b606f4d6d8a3c1f2e0570d0426fbb`).
Its only entries are `README.txt` and `download_sample.py`. Inspected as source
material without executing it; it contains no historical bars, FX, registrations
or result bundles. The private-data dependency remains open. Existing repository
acquisition tooling remains the reviewed implementation.

## Scope

This establishes a reproducible development baseline on the VPS. It does not by
itself establish service isolation, backup recovery, broker capabilities or an
edge. Deployment evidence is a separate Phase 1 increment. No paid service, broker
SDK, financial-policy change or strategy change was introduced.
