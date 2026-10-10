# Conditional cost feasibility — 10 October 2026

This is P2.4's dated screening model for the frozen one-share hypothesis and
diagnostic whole-share quantities. It does **not** select a broker/feed, verify an
account tariff or establish executable spreads. The result is conditional:

- an IBKR tiered or Saxo prefunded-USD one-share path can fit the **£3 planned
  all-in trade-loss cap** under the explicit illustration below, but only after
  account-specific fees and measured quote/fill evidence replace the unknowns;
- Saxo Classic automatic conversion can consume most or all of that cap at modest
  US-stock notionals;
- **no complete broker/data/model/hosting stack is yet evidenced below the £10
  recurring monthly ceiling**. Unknown data, account and VPS allocations are not
  zero. No purchase or subscription is authorised.

This continues the [broker/entity capability matrix](broker-capability-matrix.md).
IBKR remains the first integration candidate and Saxo the alternative; P2.2,
P2.3 and P2.5 remain open. All sources were consulted on 10 October 2026. Vendor
pages are mutable and the actual account trade ticket, agreement, invoice and
commission events take precedence when later verified.

## Scope and accounting boundaries

The intended account remains a UK retail individual cash account, long whole
shares in US-listed ordinary stocks, £1,000 total funding and no borrowing. AAPL,
MSFT and F remain engineering symbols, not an approved universe. Prices below are
deliberately round sensitivity points, not current quotes or recommendations.

For quantity `q`, reference entry `P`, stop `K`, GBP per USD `X`, adverse
half-spread `H` and additional adverse slippage `L` on **each** fill, the existing
entry contract is represented by:

```text
planned loss GBP = X * (q * (P - K + 2 * (H + L))
                        + entry commission + exit commission
                        + per-trade FX and other charges)
```

Admission requires planned loss GBP `<= 3`. `H + L` must be rounded upward from
retained decision-time bid/ask and paper-fill evidence. A completed bar cannot
supply it. A stop is not a realised-loss guarantee, and gap, latency, protection,
cancellation/replacement and partial-fill costs need separate adverse cases. If a
broker charges each child or replacement as another order, that full minimum is
reserved until account evidence proves otherwise.

One initial GBP-to-USD conversion is an account cash cost, included in experiment
P&L and the same-cash reference. It is not charged again to every trade when USD
really remains prefunded. Automatic conversion attached to a stock settlement is
a per-trade charge in the broker-specific direction documented below. The two
cases must never be mixed.

Recurring broker/feed, historical data, model and hosting bills are compared with
the £10 monthly ceiling separately from the £3 trade-loss cap. Commission waivers
earned by trading do not make a subscription free: the commissions remain costs,
and no minimum trading volume may be manufactured to obtain a waiver.

## Published tariff candidates

### IBKR Pro / IBUK candidate

For US stocks up to 300,000 shares per month, IBKR publishes tiered commission of
$0.0035/share with a $0.35 order minimum, and fixed commission of $0.005/share with
a $1 order minimum. Both show a 1% trade-value cap. Tiered routing adds venue,
clearing, regulatory and pass-through fees; fixed pricing still lists regulatory
fees. The current page lists an SEC sale fee of `0.0000206 * sale value`, a CAT fee
of `$0.000003 * quantity`, and NSCC/DTC tiered clearing of `$0.00020/share` before
venue effects. Exact route, liquidity and account charges remain unknown.
[IBKR US stock commissions][ib-stock]

The low-volume formulas are therefore lower bounds:

```text
tiered side commission = min(max(0.0035 * q, 0.35), 0.01 * q * P)
fixed side commission  = min(max(0.0050 * q, 1.00), 0.01 * q * P)
sale regulatory floor  = 0.0000206 * q * exit price + 0.000003 * q
```

The 1% cap explains why a very low-priced one-share order can cost less than the
headline minimum. Tiered venue rebates are never assumed and possible extra
charges are not netted away before actual final commission evidence exists. The
same schedule says directed API orders cannot use tiered pricing, while SmartRouted
API orders can use tiered or fixed; modifications and overnight-persistent orders
can incur another minimum. Protective/cancel-replace stress must therefore reserve
additional minima until the selected route and lifecycle are verified.

IBKR spot FX publishes 0.20 basis point of trade value with a $2 minimum at the
lowest volume tier. A single small **manual** prefunding conversion therefore has
a $2 published commission before spread. The same pricing page says AutoFX normally
adjusts the exchange rate by 0.03% without a separate commission. IBUK's cash-account
terms say an underfunded purchase currency triggers AutoFX, while supported-currency
sale proceeds are not immediately reconverted. Model AutoFX as a separate cash-flow
path, never as free FX or as the $2 manual route. Its actual cash/account behavior
remains G04. [IBKR spot FX][ib-fx] [IBUK AutoFX terms][ib-autofx]

IBKR's non-professional table offers direct top-of-book (NBBO) Networks A, B and C
at $1.50/month each: $4.50 for all three, or $3 for the Nasdaq/NYSE networks that
cover the three current engineering symbols. It also offers a broader route through
the $10/month US Securities Snapshot and Futures Value Bundle plus the $4.50/month
US Equity and Options Add-On Streaming Bundle. The base can be waived above $30
monthly commissions and the add-on above $5, but low activity must budget the full
**$14.50/month** for that bundle route. Complimentary non-consolidated quotes exist,
but are not yet shown to meet the forward-feed, spread and best-quote contract.
[IBKR market data][ib-data]

### Saxo UK Classic candidate

Saxo currently advertises Classic US stock commission of 0.08% with no minimum.
Its detailed page says displayed prices are indicative and the account trade ticket
contains exact pricing. The public lower-bound formula is therefore
`0.0008 * q * P` on each side, plus any account/instrument charges not exposed by
the page. [Saxo stocks][saxo-stock]

The UK general-fees page publishes Classic automatic currency conversion at 0.60%
on cash-stock payments, charged around the FX mid-price. Cash transfer between
different currency accounts is listed at 0.25%. It also lists 0.12% annual custody
for UK Classic stock positions, calculated daily and charged monthly, and no
inactivity fee. [Saxo charges][saxo-fees]

Classic cannot be treated as a prefunded multi-currency path without evidence:
Saxo's account page says currency subaccounts are limited to Platinum and VIP;
Platinum's deposit threshold is £200,000, outside this project's allocation.
Whether a usable USD-denominated Classic main account or another cash-only route
exists for Derek remains G01/G04. [Saxo account tiers][saxo-account]

Saxo's public API material does not expose an exact UK retail API market-data bill.
That recurring amount, entitlements and non-display/model rights remain unknown.

## Reproducible one-share screen

This sensitivity table uses `q = 1`, `X = 0.75 GBP/USD`, unchanged entry and exit
reference prices, and `H + L = $0.05/share/fill`. Thus the execution allowance is
$0.10 round trip. The FX value is a round scenario, not a market observation. The
IBKR rows include the published SEC/CAT sale floor and tiered NSCC/DTC clearing,
but exclude unknown tiered venue and pass-through outcomes. Saxo automatic FX
approximates 0.60% on both equal-price settlements. All figures are lower bounds
rounded here for display.

The IBKR table is the prefunded-USD case. If AutoFX funds an entry, add 0.03% of
the converted amount (about $0.003/$0.03/$0.075/$0.15 at the four one-share
notionals) and retain the resulting USD cash/proceeds according to verified account
behavior. Do not invent an automatic conversion back to GBP.

| USD share price | IBKR tiered cost GBP / stop headroom USD | IBKR fixed cost GBP / stop headroom USD | Saxo prefunded cost GBP / stop headroom USD | Saxo automatic-FX cost GBP / stop headroom USD |
| ---: | ---: | ---: | ---: | ---: |
| 10 | 0.23 / 3.70 | 0.23 / 3.70 | 0.09 / 3.88 | 0.18 / 3.76 |
| 100 | 0.60 / 3.20 | 1.58 / 1.90 | 0.20 / 3.74 | 1.10 / 2.54 |
| 250 | 0.60 / 3.19 | 1.58 / 1.89 | 0.38 / 3.50 | 2.63 / 0.50 |
| 500 | 0.61 / 3.19 | 1.58 / 1.89 | 0.68 / 3.10 | 5.18 / **none** |

“Stop headroom” is `(3 / X - modelled costs USD) / q`; the actual `P - K`
must not exceed it. Negative headroom means the illustrated costs alone exceed
£3. These rows do not pass a candidate: measured spread, separate slippage stress,
route fees, exact exit notional and account tariffs are still absent.

Diagnostic quantities use the same formula and the existing £500 exposure cap:

```text
q <= floor(500 / (X * (P + H + L)))
per-share stop headroom = (3 / X - all non-stop costs USD) / q
```

Applying the maximum whole quantity from that expression to the same round-price
screen gives:

| USD share price | Maximum quantity | IBKR tiered stop headroom USD/share | IBKR fixed stop headroom USD/share | Saxo prefunded stop headroom USD/share | Saxo automatic-FX stop headroom USD/share |
| ---: | ---: | ---: | ---: | ---: | ---: |
| 10 | 66 | **none** | **none** | **none** | **none** |
| 100 | 6 | 0.45 | 0.23 | 0.41 | **none** |
| 250 | 2 | 1.54 | 0.89 | 1.50 | **none** |
| 500 | 1 | 3.19 | 1.89 | 3.10 | **none** |

Increasing quantity can lower a commission minimum per share, but multiplies the
price-to-stop, spread and slippage terms. A quantity is infeasible whenever the
non-stop terms alone consume `3 / X`; it must be rejected, not rescued by narrowing
the frozen stop or weakening the cap. The actual diagnostic price/quantity grid is
an owner/P2.5 universe choice and must be evaluated from retained quotes.

## Diagnosis of the eight retained rejections

The three registered engineering cases used one share and fixed USD charges:

| Case | Fees plus two-fill slippage USD | Implied cost GBP | Maximum price-to-stop distance left USD |
| --- | ---: | ---: | ---: |
| Base | 2.12 | 1.57 | 1.93 |
| Stress | 2.72 | 2.01 | 1.33 |
| Severe | 3.42 | 2.53 | 0.63 |

The GBP conversion uses the retained funding record (`£400 * 0.9997 / $540.41`),
which gives an approximate `0.7399567 GBP/USD` presentation proxy after cent
rounding. At that reference, base fees/slippage leave about $1.93 for the one-share
price-to-stop component. The simulator uses each candidate's timestamped FX, adds
two adverse price allowances around the frozen entry/stop and recorded the trade
loss limit for all eight base candidates. The aggregate evidence therefore proves
that each total exceeded £3, but not that every exact stop threshold was $1.93.
Fees/slippage were material but were not the sole loss component; the opening-range
stop contribution exhausted the remaining candidate-specific balance.

The retained result bundles and per-candidate traces are still missing on ATLAS,
so this public record cannot honestly list the eight exact stop distances or split
each timestamp's FX contribution. Stress and severe results being identical only
show that the candidates were already blocked. They do not validate any tariff.
An IBKR tiered lower bound would release about $1.32 versus the registered base
fees at ordinary-price one-share orders, but it cannot establish that any candidate
would pass once real spread, route and fill evidence is added. No rerun or strategy
tuning was performed for this cost screen.

## Recurring monthly ceiling

The project ceiling covers the complete external stack, not only broker platform
fees. USD rows are shown at the same 0.70/0.75/0.80 GBP-per-USD sensitivity range.

| Component | Published or required monthly amount | GBP sensitivity / status |
| --- | ---: | --- |
| IBKR direct Networks A/B/C top-of-book | $1.50 each; $4.50 for all three | £3.15 / £3.38 / £3.60; leaves £6.40–£6.85 for every other recurring component, subject to account/API rights |
| IBKR snapshot plus streaming-add-on route | $14.50 before waiver | £10.15 / £10.88 / £11.60; exceeds £10 before any VPS/model allocation |
| IBKR complimentary non-consolidated quotes | $0 published | Cost fits, but feed completeness/spread acceptance is unproved; not a qualified substitute |
| Saxo UK API market data | Unknown | **Fail closed** pending exact account/API invoice and rights |
| Massive real-time NBBO/quotes | $199 Stocks Advanced | £139.30 / £149.25 / £159.20; outside the ceiling |
| Massive Basic historical/EOD tier | $0 | Not a timely forward NBBO feed; cannot replace execution quotes |
| Existing Massive account | Private current invoice/plan unknown | **Fail closed**; an existing subscription is not zero allocated cost |
| Existing ATLAS VPS | Existing bill and project allocation unknown | **Fail closed** pending invoice and a consistent allocation rule |
| Trading model/API | £0 while no model service is enabled | Current baseline uses no paid model; P6.4 provider, usage cap and invoice remain owner-gated |
| Saxo custody | 0.12% p.a. of daily stock value | About £0.05/month at the £500 exposure ceiling, before account-specific tax/rounding |

Massive documents that real-time NBBO is available on Stocks Advanced and not on
Basic, Starter or Developer; the published monthly price is $199. This disqualifies
it as a standalone forward quote source under the current ceiling, irrespective of
the useful historical access already demonstrated. [Massive pricing][massive-price]
[Massive last quote][massive-nbbo]

The recurring conclusion is therefore **unresolved on current evidence**. IBKR's
direct-network route is a plausible fit, but no complete stack is evidenced to
pass until the selected network/API rights and existing VPS/project allocation are
known. A future
P2.5 selection may not omit hosting, reuse a private subscription at zero, assume
commission waivers or silently raise the £10 ceiling.

## Closure evidence and handoff

P2.4's public, reproducible screen is complete. It establishes constraints, not a
paper-ready path. Before P2.5 can recommend proceed/revise/stop, retain a redacted
record of:

1. exact entity, account tier/base currency, commission plan and trade-ticket
   estimates for the selected IDs and whole quantities;
2. final entry, exit, protective, cancellation/replacement, exchange/regulatory
   and FX charges from supported account documentation or observations;
3. timestamped bid/ask samples and adverse fill/latency assumptions for the chosen
   session, including gaps and partial fills;
4. exact broker/API data package, professional status, rights and monthly invoice;
5. Massive, VPS, backup and future model invoices with an explicit project
   allocation; and
6. rerun decomposition from the retained registered bundles without changing the
   hypothesis, stop, £3 cap or any halt.

G01–G06 in the capability matrix remain open. No account was accessed, funded or
changed; no quote subscription, model service or hosting upgrade was purchased;
no paper or live order was sent. Live execution remains disabled.

[ib-stock]: https://www.interactivebrokers.co.uk/en/pricing/commissions-stocks.php
[ib-fx]: https://www.interactivebrokers.co.uk/en/pricing/commissions-spot-currencies.php
[ib-autofx]: https://www.interactivebrokers.co.uk/Universal/servlet/Registration_v2.formSampleView?formdb=3066
[ib-data]: https://www.interactivebrokers.co.uk/en/pricing/market-data-pricing.php
[saxo-stock]: https://www.home.saxo/en-gb/products/stocks
[saxo-fees]: https://www.home.saxo/en-gb/rates-and-conditions/commissions-charges-and-margin-schedule
[saxo-account]: https://www.home.saxo/en-gb/accounts/individual
[massive-price]: https://massive.com/pricing?product=stocks
[massive-nbbo]: https://massive.com/docs/rest/stocks/trades-quotes/last-quote?assetClass=stocks&license=personal&name=stocks_basic
