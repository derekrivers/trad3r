# Broker/entity capability matrix — 10 October 2026

P2.1's public research deliverable and P2.2's documented capability/gap record.
**IBKR remains the first integration candidate; Saxo remains the alternative.**
Neither is a verified connected-paper path. P2.1's matrix is complete; P2.2 stays
in progress until the account-specific evidence below is obtained. P2.5's owner
selection and Phase 2 exit gate remain open. The [P2.4 cost screen](cost-feasibility.md)
now records explicitly conditional tariffs and measured-data gaps.

Scope: UK retail individual, ordinary taxable account, whole US-listed ordinary
shares, long only, cash funded. No margin, CFDs, derivatives or fractional-share
dependency. AAPL, MSFT and F are existing engineering symbols, not an approved
paper universe. No account was accessed, opened or funded; no API application,
subscription or order was created. Live execution remains disabled.

This updates the [4 October feasibility research][prior] in the canonical
[plan's Phase 2](project-plan.md#phase-2-establish-broker-and-data-feasibility).
Saxo is compared because it offers an alternative API/authentication route and
potentially different small-order economics. No broader broker search is needed
until these candidates fail a requirement. Published facts below were consulted
on **10 October 2026**; the date is a research date, not a vendor effective-date
warranty. Linked vendor documentation is mutable. Reverify before account choice
and freeze the exact API/server versions before adapter qualification.

## Evidence levels

- **Documented:** the cited primary source describes the feature. It does not
  establish Derek's entitlement or demonstrate actual behavior.
- **Unverified:** requires account terms, a supported read-only observation or an
  owner-authorised connected-paper rehearsal. An unknown must block its dependent
  gate, rather than become a default capability.
- **Project requirement:** our inference or acceptance criterion, not a promise
  made by either broker. Existing synthetic tests prove only our supplied-input
  contract. No broker row below is marked tested.

## P2.1 — Entity, account and access

| Requirement | IBKR candidate | Saxo alternative | Evidence still required |
| --- | --- | --- | --- |
| UK entity and carrying arrangement | Interactive Brokers (U.K.) Limited (IBUK), FCA 208159. Its retail service guide describes the principal stock account as introduced by IBUK and carried/executed/custodied by Interactive Brokers LLC under a three-party agreement. An ISA has a different arrangement. [Disclosure][ib-legal], [service guide][ib-entity] | Saxo Capital Markets UK Ltd, FCA 551422, per the UK disclosure. Group OpenAPI documentation does not establish an individual UK customer's agreement or custody arrangement. [UK disclosure][saxo-entity] | Actual agreement/entity, residency eligibility, retail classification, account restrictions, custody and compensation terms. Do not infer these from the website hostname. |
| Regulatory permissions | Official broker disclosure identifies FCA authorisation. [FCA firm record][ib-fca] was attempted but returned no usable permissions detail. | Official broker disclosure identifies FCA authorisation. [FCA firm record][saxo-fca] likewise returned no usable permissions detail. | Full current permissions/restrictions check remains open for both; disclosure is not an independent permissions audit. |
| Account and currencies | Proposed individual **cash** account with GBP valuation and sufficient settled USD. The published account configuration allows different currencies but requires settled cash to enter trades. [Account configuration][ib-cash] | Proposed ordinary investment account with cash-only stock permissions and a usable USD account/subaccount. Neither the precise account configuration nor its no-borrowing behavior is established by public API documentation. [Account details][saxo-account] | Confirm no credit/short permissions relied on, USD retention, cash field meanings, FX behavior and all applicable charges. GBP base currency alone does not convert or settle USD. |
| API route | Official Python TWS socket API through TWS or IB Gateway; requirements specify an opened, funded IBKR Pro account. [API introduction][ib-api], [requirements][ib-requirements] | OpenAPI with HTTP requests and streaming; separate SIM and LIVE environments. [Environments][saxo-env], [streaming][saxo-stream] | Pin supported versions and demonstrate access for the exact entity/account. An available chat plugin does not provide the project's durable execution adapter. |
| Paper prerequisites | Paper permissions/subscriptions/configuration follow the regular account. Public paper guidance is inconsistent about when funding is needed: its lesson says both funded and approved-before-funding; API requirements explicitly require funding. Budget for the stricter API prerequisite until broker confirmation. [Paper guide][ib-paper], [lesson][ib-paper-lesson], [requirements][ib-requirements] | Developer SIM supports testing; requesting personal LIVE application credentials requires a SIM application and a funded live account. This is a later prerequisite, not permission to request LIVE access. [Direct-client process][saxo-app] | Owner confirms existing access without supplying secrets in chat. Do not open/fund an account to resolve this research gap. Verify paper identity from broker-supported evidence before any submission. |
| Login and reauthentication | GUI username/password login; supported headless Gateway login is absent. Daily autorestart and weekly manual reauthentication are documented. Gateway text mentions the weekend reset; settings text describes a Monday cycle. Treat the exact expiry schedule as version/account dependent. [Gateway][ib-gateway], [reauthentication][ib-auth] | OAuth authorization-code flow issues access/refresh tokens; refresh within returned lifetimes and store the replacement pair. Sample lifetimes are not account guarantees. [OAuth][saxo-auth] | Owner login/2FA route, expiry/revocation recovery, restart behavior, competing sessions and availability. Do not assume an unattended VPS process can renew forever. |
| Paper realism and data | Simulated fills use top-of-book; stops are simulated; some partial-fill behavior differs from production. Paper trades do not settle at a clearing house. [Paper guide][ib-paper] | SIM omits some reporting and market data; selected history/report services offer mock data. A mock response cannot establish settlement or fee fidelity. [Environments][saxo-env], [mock data][saxo-mock] | Qualified forward quotes/FX and retained actual-paper account observations. Neither simulator establishes executable prices, live protection or settlement fidelity. |
| Feed rights | Paper inherits subscriptions, but actual API/forward entitlements remain P2.3. [Paper guide][ib-paper] | API price feeds require additional licences/agreements and can cost more than platform display data. [Business concepts][saxo-concepts] | Exact data package, subscriber classification, API/non-display use, retention and external-model rights; no assumption that Massive history or a screen quote licenses execution data. |

Published demo balances exceed this project's allocation. [IBKR paper][ib-paper],
[Saxo SIM][saxo-env]. The future paper controller
must reconcile a **£1,000 research allocation** without adopting broker demo buying
power or resetting risk history. Retain the £300 cumulative, £10 session, £25 weekly
and £3 all-in planned-trade limits. No loss budget, halt, settlement policy or
existing owner gate changes through this document.

## P2.2 — Execution and account evidence

| Capability | IBKR documented surface | Saxo documented surface | Project acceptance / unresolved fact |
| --- | --- | --- | --- |
| Instrument identity | `conId` plus exchange; full stock qualification includes security type, currency and primary exchange. [Contract][ib-contract] | `Uic` **and** `AssetType`; a stock and its CFD can share a UIC. Only entitled instruments are returned. [Reference data][saxo-reference] | Retain qualified IDs for the approved universe, route and currency. Reject CFD substitution and symbol-only matching. Current account-specific IDs are unverified. |
| Quantity and price increments | `contractDetails.minTick` is the smallest increment, not the complete price ladder; exchange-aligned `marketRuleIDs` and `reqMarketRule` supply price-dependent rules. [Market rules][ib-ticks] | Instrument details supply order validation/formatting; amount/lot and minimum-value restrictions vary by instrument. [Reference data][saxo-reference], [orders][saxo-orders] | Whole shares only; retain minimum size, lot/size step, tick ladder, order types and duration for each actual instrument. No hard-coded one-cent tick or assumed one-share permission. |
| Protective orders | Attached profit-taker/stop-loss orders are documented through `parentId`; construction/transmission needs deliberate sequencing. [Attached orders][ib-bracket] | Related limit and stop orders exist; allowed order types vary by instrument and relating exits to an existing position depends on netting mode. [Orders][saxo-orders] | Verify activation after partial entry, held vs working state, quantity adjustment, trigger method, regular-session scope and behavior during disconnect. A stop is not a guaranteed loss bound; a stop-limit can remain unfilled. |
| Partial fills and identities | `execDetails` supplies executions; `orderStatus` includes filled/remaining, client and permanent order IDs and may be duplicated. Corrections can arrive with a changed execution-ID suffix. [Executions][ib-executions], [status][ib-status], [corrections][ib-corrections] | Audit order activities include `OrderId`, event `LogId`, per-event `FillAmount`, cumulative `FilledAmount` and position identity. [Audit][saxo-audit] | Preserve raw events, correlate intent/client/broker IDs and account; deduplicate without counting a correction as another fill. Broker correction/bust handling needs a reviewed mapping to our immutable evidence model. |
| Cancel/replace and manual orders | Modification uses existing order identity; `permId` identifies the order within an account. Binding manual/other-session orders can cancel/resubmit and lose queue priority; `reqAllOpenOrders` does not bind them. [Modification][ib-modify] | Order audit distinguishes confirmed/rejected changes and cancellations. [Audit][saxo-audit] | Cancellation acceptance alone releases nothing. Rehearse cancel/fill races, unknown outcomes, permission to affect other-session orders and terminal cumulative evidence. No automatic replacement while earlier quantity may remain working. |
| Commission evidence | Execution-linked commission/fees reports include execution ID and currency. Current prose and sample callback names differ (`commissionReport` / `commissionAndFeesReport`). [Fees report][ib-commission] | Trade details offers a trade-specific PDF; it is not proof of a machine-readable, execution-linked final commission stream. [Trade details][saxo-trade] | Pin actual API schema. Verify late fees, finality, revisions, currencies and transaction/report joins; keep reserves until established. Neither cited surface proves our synthetic `fees_final` assertion. Saxo's required structured fee mapping is unresolved. |
| Currency cash and equity | Account updates distinguish `CashBalance`, `AvailableFunds`, `BuyingPower`, account readiness and other keys. These are not interchangeable. [Account values][ib-values] | Accounts/balances surface exists; unsettled amounts describes currency/value-date cash flows, with examples for partners handling settlement. [Account details][saxo-account], [unsettled amounts][saxo-unsettled] | Prove retail entitlement, per-currency settled/unsettled amounts, pending fees, equity/FX timing and cash-flow adjustments. Do not treat a partner example as retail availability or buying power as settled USD. |
| Settlement | US stock standard settlement is T+1; a paper account does not perform actual clearing-house settlement. [SEC][sec-settlement], [paper guide][ib-paper] | Same US-market standard; exact customer-account value dates and usable-cash policy remain unverified. [SEC][sec-settlement], [unsettled amounts][saxo-unsettled] | Reconcile actual credits and failed/delayed settlement, currency calendars and FX settlement separately. The repo's conservative release policy remains in force; durable cash release remains P4.6. |
| Startup and current state | Open-order, completed-order, execution and account/position queries are distinct. Completed-order query covers the given day. [API index][ib-api], [completed orders][ib-completed] | Portfolio orders/positions plus audit order history and streaming are distinct surfaces. [Portfolio][saxo-portfolio], [audit][saxo-audit], [streaming][saxo-stream] | Establish snapshot end/completeness, all relevant accounts/clients/manual activity, pagination and stream gap recovery. An empty open-order list never resolves a possibly sent order. |
| Recovery horizon | Execution overview documents current-day default, TWS configurable up to seven days and **Gateway current-day only**. The request-method page states current-day only. [Execution overview][ib-executions], [request method][ib-execution-request] | Audit documentation describes 2+ years of order activities but no streaming on that endpoint. [Audit][saxo-audit] | No assumption of unlimited historical replay. IBKR needs a verified supplementary statement/history path across midnight; Saxo needs proof that retained activities join to final fees/cash. Query retention and outage recovery must be tested on the pinned version. |

The account-configuration page still describes stock-sale cash availability as
three business days, while the SEC source establishes the US T+1 standard. Treat
this as an unresolved documentation/account-policy discrepancy, not authority to
change either our calendar or the broker cash-release mapping. Obtain current
account-specific evidence under G04. [Account configuration][ib-cash],
[SEC settlement standard][sec-settlement].

## Adapter consequences and closure evidence

These are engineering requirements inferred from the matrix, not implemented
broker behavior. They supplement the [paper gates](paper-readiness.md) without
changing [synthetic reconciliation](order-reconciliation.md) or
[protection acceptance](order-protection-acceptance.md).

1. **Authenticate and identify before arming.** Retain a private evidence record
   of legal entity, account type, paper identity, permissions, API version and
   credential ownership. A port, URL, account-name prefix or user label alone is
   insufficient. Failed authentication leaves entries disarmed.
2. **Rebuild complete state.** Join orders, executions, corrected executions,
   fees, qualified positions, currency cash and settlement across the outage.
   Establish completion boundaries; conflicting or missing history keeps the
   account blocked. A current-day Gateway replay cannot bridge an overnight gap
   by declaring absent executions to be zero.
3. **Map economic events explicitly.** Our synthetic cumulative snapshots are not
   raw broker callbacks. Specify correction/bust identity, fee revision/finality,
   raw-event retention and atomic ledger updates before implementing the adapter.
   Preserve every existing halt and attempt. No silent repair of contradictory
   retained executions is authorised.
4. **Prove quantity protection.** Run the applicable X01–X24 cases on the approved
   paper environment, including parent partial fills, late fee evidence, stop
   rejection, unknown submissions, manual activity, cancel/fill races and restart.
   Keep the shared sell reservation: broker OCO/bracket support does not by itself
   justify two independently executable exits for the same holding.
5. **Prove cash rather than infer it.** Establish the meaning and freshness of
   each balance field and exact settled-cash evidence before releasing pending
   sale proceeds. P4.6's reviewed durable transition remains a separate gate.

| Gap | Owner / dependency | Closure evidence | Blocks |
| --- | --- | --- | --- |
| G01 Exact entity/account and permissions | Derek supplies existing non-secret account facts; agent checks current agreement and full FCA record | Dated private agreement/permissions evidence and public redacted conclusion | P2.2 verification, P2.5 selection |
| G02 Paper/API access and auth operations | Existing access facts first; account creation/funding and connected submissions require separate owner authority | Supported account/environment proof; pinned version and witnessed login/expiry/recovery drill | P5.1/P5.6 |
| G03 Instrument and protection semantics | Account metadata/terms now; explicit permission before later paper orders | P2.2: qualified metadata and supported order semantics; P5: paper lifecycle/partial-fill/race results | P2.2 account mapping; P5.3/P5.7 operational proof |
| G04 Cash, settlement and fee finality | Account documentation/statements and a reviewed mapping; later authorised paper observations | P2.2: field/fee/value-date contract; P5: reconciled buy/sell/fees/FX trace with no unexplained difference | P2.2 account mapping; P4.6/P5 reconciliation |
| G05 Overnight history and corrections | Broker-supported query/report availability | Restart spanning midnight and outage beyond query horizon; corrected execution and late fee trace | Connected restart readiness |
| G06 Forward data and rights | P2.3; broker/feed entitlement and terms | Quote/FX coverage, timestamps, usage/retention/model rights and exact recurring tariff | Qualified economics and P5.2 |
| G07 Costs and owner decision | P2.4 then P2.5 | Dated intended-quantity costs, FX scenarios and total recurring bills; Derek's decision | Phase 2 exit |

P2.2 account mapping uses supported documentation and available read-only evidence.
P2.5 must explicitly record any remaining operational conditions; order-based
rehearsals belong to P5 after owner approval. This table does not require placing
paper orders to select a candidate or authorise those orders by implication.

A redacted evidence record should name the gap, observation date, source/version,
account alias, method, result, private evidence location/hash and reviewer. Never
commit account numbers, credentials, broker reports or licensed price samples.
No broker contact or owner message was sent by this research.

## P2.4 delivery and remaining handoff

The [dated P2.4 model](cost-feasibility.md) screens the frozen one-share hypothesis
and diagnostic whole-share sizes separately. It covers account-tariff candidates,
entry/exit minima, third-party fees, spread,
slippage, protective/cancellation/replacement costs where applicable, conversion
and currency holding costs. Separate prefunded USD from per-trade conversion.
Include data, model and the existing VPS allocation in the **£10 monthly ceiling**;
unknown costs are not zero. Diagnose the eight previously risk-rejected candidates
without replacing absent registered inputs or tuning the strategy to make trades.

The dated public matrix and conditional P2.4 screen are delivered. Account-specific
P2.2/P2.3 verification and the Phase 2 exit are **not complete**. G01–G06 and the
recurring invoice/allocation gaps remain explicit; neither document establishes an
executable account/feed choice.

[prior]: https://chatgpt.com/space/page_69ec178972dc8191a2aabe3d647feb65
[ib-legal]: https://www.interactivebrokers.co.uk/en/general/disclaimers.php
[ib-entity]: https://www.interactivebrokers.co.uk/en/accounts/forms-and-disclosures-services-guide.php
[ib-fca]: https://register.fca.org.uk/s/firm?id=001b000000MfKjCAAV
[saxo-fca]: https://register.fca.org.uk/s/firm?id=001b000000NMcpXAAT
[saxo-entity]: https://www.home.saxo/en-gb
[ib-cash]: https://www.interactivebrokers.co.uk/en/accounts/configuring-your-account.php
[ib-api]: https://www.interactivebrokers.com/docs/tws-api/doc/introduction
[ib-requirements]: https://www.interactivebrokers.com/docs/tws-api/doc/notes-limitations/requirements
[ib-paper]: https://www.ibkrguides.com/orgportal/aboutpapertradingaccount.htm
[ib-paper-lesson]: https://www.interactivebrokers.com/campus/trading-lessons/how-to-open-an-ibkr-paper-trading-account/
[ib-gateway]: https://www.interactivebrokers.com/docs/tws-api/doc/architecture/the-trader-workstation/the-ib-gateway
[ib-auth]: https://www.interactivebrokers.com/docs/tws-api/doc/tws-settings/daily-weekly-reauthentication
[ib-contract]: https://www.interactivebrokers.com/docs/tws-api/doc/contracts-financial-instruments/the-contract-object
[ib-ticks]: https://www.interactivebrokers.com/docs/tws-api/doc/orders/minimum-price-increment/introduction
[ib-bracket]: https://www.interactivebrokers.com/docs/tws-api/doc/orders/place-order/adding-a-profit-taker-and-stop-loss
[ib-executions]: https://www.interactivebrokers.com/docs/tws-api/doc/order-management/execution-details/introduction
[ib-execution-request]: https://www.interactivebrokers.com/docs/tws-api/doc/order-management/execution-details/request-execution-details
[ib-status]: https://www.interactivebrokers.com/docs/tws-api/doc/order-management/order-status/introduction
[ib-corrections]: https://www.interactivebrokers.com/docs/tws-api/doc/order-management/execution-details/exec-id-behavior
[ib-modify]: https://www.interactivebrokers.com/docs/tws-api/doc/orders/modifying-orders
[ib-commission]: https://www.interactivebrokers.com/docs/tws-api/doc/order-management/commission-and-fees-report
[ib-values]: https://www.interactivebrokers.com/docs/tws-api/doc/account-portfolio-data/account-updates/account-value-keys
[ib-completed]: https://www.interactivebrokers.com/docs/tws-api/doc/order-management/retrieving-completed-orders/introduction
[saxo-env]: https://www.developer.saxo/openapi/learn/environments
[saxo-stream]: https://www.developer.saxo/openapi/learn/streaming
[saxo-app]: https://www.developer.saxo/openapi/learn/direct-clients-request-for-openapi-application-credentials-for-the-live-environ
[saxo-auth]: https://www.developer.saxo/openapi/learn/oauth-authorization-code-grant
[saxo-mock]: https://www.developer.saxo/openapi/learn/mock-data-in-simulation
[saxo-concepts]: https://www.developer.saxo/openapi/learn/core-business-concepts
[saxo-reference]: https://www.developer.saxo/openapi/learn/reference-data
[saxo-orders]: https://www.developer.saxo/openapi/learn/order-placement
[saxo-audit]: https://www.developer.saxo/openapi/learn/audit-orderactivities
[saxo-trade]: https://www.developer.saxo/openapi/learn/trade-details
[saxo-account]: https://www.developer.saxo/openapi/learn/account-details
[saxo-unsettled]: https://www.developer.saxo/openapi/learn/unsettled-amounts
[saxo-portfolio]: https://www.developer.saxo/openapi/learn/orders-and-positions
[sec-settlement]: https://www.sec.gov/newsroom/press-releases/2024-62
