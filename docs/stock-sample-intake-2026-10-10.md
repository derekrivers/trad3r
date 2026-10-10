# Original stock sample received on ATLAS — 10 October 2026

The owner supplied `trad3r_sample_20261004T160256652430Z.zip` after the initial VPS
milestone. Its SHA-256 exactly matches the original [sample contract](data.md) and
[4 October validation](validation.md):
`eebd9e7454227356d9b7d1bcbe9e1518bcd18721fdf441a9179e19a3b534074b`.
This supersedes the missing-stock-input finding in the earlier 10 October inventory;
those earlier observations remain historical records.

Retained an exact root-private copy at:
`/var/lib/trad3r/sources/eebd9e7454227356d9b7d1bcbe9e1518bcd18721fdf441a9179e19a3b534074b/trad3r_sample_20261004T160256652430Z.zip`.
The containing directory is 0700 and the archive 0400. The attachment was preserved,
the copy rehashed, and ZIP payloads were read without extraction or executing any
archive content. No licensed bars, archive or journals were added to git.

## Actual VPS checks

Used Python 3.12.3 and revision `8ebda1a815d76b888f13217b17b8997de781a54f`;
shipped Python fingerprint remains
`9ecd1a50bdd305c0ed7195cfb999cd9fc4e47d40a36598b40b7ac0c844d88e9a`.

| Check | Result |
| --- | --- |
| Archive identity | Matches recorded original stock archive exactly |
| `validate ARCHIVE --require-complete` | Exit 0; payload hashes, inventory, schema, prices, ordering and declared scheduled coverage pass |
| `research-audit ARCHIVE --start 2026-09-04 --end 2026-10-02` | Exit 0; full requested window structurally complete, including all scheduled sessions |
| Symbols / sessions | AAPL, MSFT and F; 20 sessions per symbol |
| Regular-session raw minute observations | 23,400; 7,800 per symbol; zero missing scheduled minutes |
| Two strict per-bar replays | Both exit 0; byte-identical journals, matching the original recorded replay hash |

Replay journal SHA-256:
`cf33c5bb2e5f2cb104f4c3d488081a081abeb42834dcbe51df5b93c8a6700c84`.
Private validation, full-window audit and both replay reports/journals are retained
under `/var/lib/trad3r/evidence/20261010-stock-intake/`. No strategy outcomes were
computed. The archive is still already-inspected engineering data; structural
completeness does not establish an untouched holdout, independent price accuracy,
point-in-time delivery or a trading edge.

## Remaining historical inputs

The archive contains stock raw/split-adjusted payloads, manifest and validation
metadata. It contains no GBP/USD observations, experiment assumptions,
registrations or result bundles. The stock transfer is complete; the registered
historical backtests are not yet reproducible on ATLAS.

Next retain and verify either the original combined stock/FX archive with SHA-256
`6ba4e7fca0e6b875997d6a7ac81ede3f2356dedbb72f1ead73edce80dbc24f8a`, or the original FX
export for reconstruction and verification. The recorded connector CSV hash is
`6559a3fefc27181ed4b42ab965396cda13c58049b861dfdbdd502a0647fc87a7`.
Also retain the original assumptions, registrations and result bundles against the
identities in [first-engineering-results.md](first-engineering-results.md). A new
reproduction must use its explicitly registered matching code and costs; do not
invent FX or silently substitute example assumptions.

Design v2 and off-host backup remain separate open dependencies. This local source
copy is not an off-host backup. No new account, paid acquisition, broker submission,
risk-policy change or recurring job was introduced.
