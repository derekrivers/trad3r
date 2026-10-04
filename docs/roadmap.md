# Delivery roadmap

This repository holds implementation and engineering acceptance notes. The owner's
existing project charter and research records retain financial decisions; this
initial engineering snapshot does not declare unresolved planning gates complete.

| Phase | Scope | Current state |
| --- | --- | --- |
| 0 | Charter and risk policy | Agreed for planning |
| 1 | Broker and data economics | Conditional IBKR candidate; account-specific checks open |
| 2 | Offline CLI foundation | First increment: sample reader, deterministic bar replay, risk arithmetic |
| 3 | Data pipeline | First private sample structurally checked; broader validation open |
| 4 | One baseline strategy | Not started |
| 5 | Independent strategy validation | Not started |
| 6 | Optional classifier | Not started; begin in shadow mode |
| 7 | Broker execution and recovery | Not started |
| 8 | Forward paper trial | Not started |
| 9 | Restricted live review | Disabled; separate decision required |

The offline foundation can proceed using the accepted sample without funding a
brokerage account. It does not waive the full Phase 1 broker feasibility gate.

## Next implementation increment

1. Add a Decimal cash/position ledger with realised and unrealised P&L, per-currency
   balances, explicit FX observations, fees and settlement calendars.
2. Define conservative simulated fills, completed-bar event batches, entry/exit
   sequencing and ambiguous intraminute stop/target handling.
3. Persist risk baselines and halt state; test restart and cash-flow invariants.
4. Add quantity/exposure/settled-cash controls and verify the £3 all-in trade budget.
5. Introduce one frozen strategy hypothesis and report net results only after those
   accounting and execution semantics are verified.

No broker credentials or news-classification service are needed for this increment.
Jev is a later optional classifier; its confidence is not a probability of profit.
