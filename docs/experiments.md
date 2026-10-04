# Registered engineering experiments

Use an experiment registration to freeze a complete source window, one selected
symbol, the strategy/policy versions, risk amounts, code fingerprint and explicit
economic assumptions before running the baseline. This workflow is exclusively
for engineering scenarios on inspected data. It does not certify an untouched
holdout, a profitable strategy, or readiness for paper/live orders.

## Register, run, inspect

Supply the combined stock/FX archive and a private assumptions file following
[preparation](preparation.md). Keep all registrations and results in ignored `runs/`:

```sh
python -m trad3r register-experiment data/combined.zip data/assumptions.json --id aapl-engineering-base-v1 --symbol AAPL --start 2026-09-04 --end 2026-10-02 --output runs/aapl-base-registration.json
python -m trad3r run-experiment runs/aapl-base-registration.json data/combined.zip data/assumptions.json --output runs/aapl-base-result.zip
python -m trad3r inspect-experiment runs/aapl-base-result.zip
```

Registration validates the prepared inputs without calling the strategy. It records
exact archive, assumptions-file and prepared-scenario hashes, the fixed hypothesis,
approved bounded rollover and all current risk amounts. The code fingerprint hashes
every shipped `trad3r/*.py` file by name and content; changing Python code requires
a new registration. Documentation-only changes do not change that fingerprint.
Retain the corresponding repository revision for reproducibility. Runtime Python
and platform versions are recorded in the result separately.

Choose and register all cost-stress variants before opening any result. Use one
preselected symbol throughout; do not switch to whichever stock subsequently wins.
Changing whitespace in an assumptions file changes its identity, even if its parsed
values are unchanged. Existing registrations/results are never overwritten. Keep
failed variants in the experiment record; a new ID is not permission to erase a
halt or present a fresh account as a continuation of an old one.

## Saved evidence and integrity

A result ZIP contains exact `registration.json` and `assumptions.json`, the prepared
`scenario.json`, complete `result.json`, compact `summary.json` and an inventory with
payload sizes and SHA-256 digests. Scenarios contain licensed FX observations and
results contain simulated price/account details, so keep the whole bundle private.
The source market archive is identified by hash and must be retained separately.

The execution command verifies code and all input identities before simulation.
It runs the existing continuous-account baseline and same-cash reference, replays
both ledgers, reconstructs metrics and checks that halts are retained across sessions.
Only then does it publish the complete bundle by an exclusive atomic hard link.
Interrupted or failed computation produces no success bundle; an existing output
causes an error before another simulation begins. The hard-link filesystem
requirement from acquisition also applies.

Inspection checks the exact inventory, every checksum, input identities, accounting,
one initial funding per counterfactual account, reconstructed metrics, session halt
continuity and summary consistency. Limits are 50 MiB compressed and 100 MiB expanded;
unknown, duplicate and nested payloads fail. Inspection does not require the current
code fingerprint to equal the recorded one, so older bundles can still be read, but
this version only understands the current strategy/policy/report contracts. It does
not rerun source market bars, independently validate prices or reconstruct every
intraminute risk path. Full coherent malicious rewriting is not prevented by hashes.
Local registration/completion timestamps are audit metadata, not authenticated proof
of preregistration or evidence that the author had never inspected those prices.

## Interpret the summary

Read both net account P&L and the difference from the same-cash no-trade reference.
USD cash can gain in GBP terms even when the simulated trades lose after costs.
Inspect trade count, rejected candidates, no-candidate days, fees, observed drawdown
and all halt reasons before interpreting any return. Zero fills can be a correct
result under the £3 all-in trade risk cap and actual opening-range width.

The registration's acceptance statement covers engineering integrity only; it has
no profitability pass threshold. The output always states `research_ready=false`
and `live_trading_enabled=false`. Qualification still requires sourced economics,
independent data checks, broader history and a registered chronological protocol.
