"""Pure GBP risk calculations; not a persistent live risk controller."""
from dataclasses import dataclass
from decimal import Decimal

D = Decimal


def money(value: str | int | Decimal) -> Decimal:
    if isinstance(value, (float, bool)):
        raise ValueError("Use decimal strings, integers or Decimal, not float/bool")
    result = D(value)
    if not result.is_finite():
        raise ValueError("Amount must be finite")
    return result


@dataclass(frozen=True)
class Policy:
    initial_capital: Decimal = D("1000")
    overall_loss: Decimal = D("300")
    daily_loss: Decimal = D("10")
    weekly_loss: Decimal = D("25")
    trade_loss: Decimal = D("3")

    def __post_init__(self):
        for name in self.__dataclass_fields__:
            value = money(getattr(self, name))
            if value <= 0:
                raise ValueError("Policy limits must be positive")
            object.__setattr__(self, name, value)


@dataclass(frozen=True)
class Mark:
    """GBP net liquidation equity and cumulative external flows after funding."""
    equity: Decimal
    deposits: Decimal = D("0")
    withdrawals: Decimal = D("0")

    def __post_init__(self):
        for name in self.__dataclass_fields__:
            value = money(getattr(self, name))
            if name != "equity" and value < 0:
                raise ValueError("Cumulative cash flows must be nonnegative")
            object.__setattr__(self, name, value)

    @property
    def adjusted_equity(self):
        return self.equity - self.deposits + self.withdrawals


@dataclass(frozen=True)
class Assessment:
    cumulative_pnl: Decimal
    daily_pnl: Decimal
    weekly_pnl: Decimal
    halt_reasons: tuple[str, ...]


def assess(mark: Mark, session_start: Mark, week_start: Mark,
           latched: tuple[str, ...] = (), policy: Policy = Policy()) -> Assessment:
    """Baseline marks must be captured before trading, never reset on restart.

    latched carries prior reasons; this function cannot clear them. Persistence,
    session calendars and owner-reviewed reset belong to a future controller.
    """
    allowed = {"overall", "daily", "weekly"}
    if not set(latched) <= allowed:
        raise ValueError("Unknown halt reason")
    for baseline in (session_start, week_start):
        if mark.deposits < baseline.deposits or mark.withdrawals < baseline.withdrawals:
            raise ValueError("Cumulative cash flows went backwards")
    cumulative = mark.adjusted_equity - policy.initial_capital
    daily = mark.adjusted_equity - session_start.adjusted_equity
    weekly = mark.adjusted_equity - week_start.adjusted_equity
    reasons = set(latched)
    for name, pnl, limit in (("overall", cumulative, policy.overall_loss),
                             ("daily", daily, policy.daily_loss),
                             ("weekly", weekly, policy.weekly_loss)):
        if pnl <= -limit:
            reasons.add(name)
    return Assessment(cumulative, daily, weekly, tuple(sorted(reasons)))


def planned_long_loss(quantity: int, entry: Decimal, stop: Decimal,
                      gbp_per_quote_currency: Decimal, round_trip_cost_gbp: Decimal) -> Decimal:
    """Estimate price-to-stop loss plus all fees/spread/slippage allowances.

    This does not guarantee a realised loss or check cash/exposure availability.
    Prices must be raw historical quote-currency prices, not split-backadjusted.
    """
    if type(quantity) is not int or quantity <= 0:
        raise ValueError("Quantity must be a positive whole share count")
    entry, stop, fx, costs = map(money, (entry, stop, gbp_per_quote_currency, round_trip_cost_gbp))
    if not 0 < stop < entry or fx <= 0 or costs < 0:
        raise ValueError("Invalid long-trade inputs")
    return quantity * (entry - stop) * fx + costs
