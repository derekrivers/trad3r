# Massive stock and FX intake — 10 October 2026

The existing root-managed Massive credential was used for one bounded,
read-only historical acquisition. No subscription change, account action or
trading action was performed. The credential remains outside the repository at
`/etc/trad3r/massive.env` with mode `0600`.

## Acquisition evidence

| Item | Result |
| --- | --- |
| Window | 2026-09-04 through 2026-10-02, inclusive |
| Requests | AAPL, MSFT, F and `C:GBPUSD`; one explicit UTC-bounded minute request per ticker |
| Stock observations | 23,400 regular-session bars; 390 per symbol per each of 20 scheduled sessions |
| FX observations | 29,654 completed-bar GBP/USD observations; source close retained and inverted with `historical-completed-bar-proxy-v1` |
| Archive | Private ATLAS path `/var/lib/trad3r/sources/massive_20261010_stock_fx.zip` |
| Archive SHA-256 | `d951b92c1a850357cd66da09bcd4af2ddd67a1a568ab291bc6b216b943e49055` |
| Retrieval evidence | `/var/lib/trad3r/evidence/20261010-massive-fx/` (private, mode `0700`) |
| Validation | `validate --require-complete` passed; `research-audit` passed structurally and remains `research_ready: false` |

The API therefore authenticated and returned both stock and currency data with
the existing entitlement. This is a successful access and coverage check, not
proof of a paid-plan term, redistribution right, independent price correctness,
point-in-time universe selection or actual delivery-time availability.

## Relationship to the supplied sample

The newly acquired stock JSONL is not byte-identical to the retained original
stock sample for AAPL, MSFT or F. The comparison is recorded privately in
`archive-comparison.json`; the original sample remains the authoritative
engineering fixture and is not replaced. The original combined FX archive or
the original FX export has not been recovered, so the new FX series cannot be
claimed as reconstruction of that missing artifact.

## Remaining gates

The archive is suitable for structural inspection and later registered
preparation. It does not close P2.3, P3.1 or P1.4: historical qualification,
independent price/corporate-action checks, untouched chronological holdout
registration, dated broker costs and the owner's original experiment files are
still absent. No strategy outcome or P&L was inspected. Live execution remains
disabled.
