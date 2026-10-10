# First historical engineering results — 4 October 2026

Historical retained results; these runs have not been reproduced on ATLAS.
See [current inventory and dependencies](project-status.md).

The three cases in the [predeclared plan](engineering-run-plan.md) completed using
the same AAPL window: 20 sessions from 4 September through 2 October 2026. All three
registrations were created before the first run. Execution used the code merged in
PR #21, main revision `7effc841f1bb266bd458ccfd8035fc3066e3b811` and code fingerprint
`4cbbcd1976737cd5a52611cb5b7b6ec93dc27805e434f3e40be37ad2b9d1aa9b`.

| Measure | Base | Stress | Severe |
| --- | ---: | ---: | ---: |
| Generated candidates | 8 | 8 | 8 |
| Rejected: planned trade loss limit | 8 | 8 | 8 |
| Closed trades | 0 | 0 | 0 |
| Realised trade P&L GBP | 0.00 | 0.00 | 0.00 |
| Net account P&L GBP | +8.49 | +8.49 | +8.49 |
| Difference from same-cash reference GBP | 0.00 | 0.00 | 0.00 |
| Explicit trading commissions GBP | 0.00 | 0.00 | 0.00 |
| Maximum observed equity drawdown GBP | 2.85 | 2.85 | 2.85 |
| Final halt reasons | None | None | None |

Money above is rounded for presentation; private bundles retain full Decimal
values. The initial hypothetical conversion used £400 and received $540.41 after
the declared rate haircut and cent rounding, leaving £600 cash in GBP. The account
gain came entirely from the changing GBP valuation of that USD cash, after the
conversion assumption. Trading contributed nothing. Observed drawdown is measured
at simulated marks; it is not a bound on unobserved intraminute movements.

The £3 all-in planned-loss cap prevented every candidate. No cap was increased,
stop narrowed, fee removed, or alternative stock selected to manufacture fills.
Identical results across the three cost cases do not show that costs are harmless:
none executed a trade. Synthetic tests exercise fills, settlement, losses and
halts; those are engineering checks, not historical performance evidence.

## Retained evidence

Combined source archive SHA-256:
`6ba4e7fca0e6b875997d6a7ac81ede3f2356dedbb72f1ead73edce80dbc24f8a`.

| Case | Registration SHA-256 | Result bundle SHA-256 |
| --- | --- | --- |
| Base | `013388e64a1ee4e5a02d62a371bdbc2438c01242ccfa039d6cb8a25ecb53abfe` | `2efd95f03740bc3fdb09202fbcd9ee4f036eb9a52393fb3fbbc07904d053d8d7` |
| Stress | `8ed5057b3fdb232ee8800f921adceae43bf6c5f74b5343c8b094aa14e0522903` | `8b16633b4f513044c2e6f494e9773cfa17b997d54dc70041f429c795a9f3f22f` |
| Severe | `f111fa599d2786f68b284d9aaa1f10eb602907fb54b5a2ff2de82e6ad21b1e07` | `7219a21e9b325b563b97599f157c2cf508bd885d3876c1c58e3ec5c95888f18e` |

Each private result includes both account journals, assumptions, prepared scenario,
registration, metrics and checksums. Both accounts reconcile, each has one initial
funding, and session/halt inventories pass inspection. Raw prices and result bundles
remain outside this public repository.

This milestone establishes a working historical engineering pipeline. It provides
no evidence of a profitable strategy, income, or forward paper readiness. Next:
qualify data and dated costs, preregister a broader chronological feasibility study,
and implement broker reconciliation/recovery before connecting any paper account.
