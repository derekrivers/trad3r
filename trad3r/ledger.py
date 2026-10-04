"""Deterministic accounting for supplied offline fills, never an execution engine."""
from copy import deepcopy
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from decimal import Decimal

from .risk import Mark, Policy, money

D = Decimal


def utc(value):
    stamp = datetime.fromisoformat(value)
    if stamp.tzinfo is None or stamp.utcoffset() != timedelta(0):
        raise ValueError("Event timestamps must be UTC")
    return stamp


def positive(value):
    value = money(value)
    if value <= 0:
        raise ValueError("Amount must be positive")
    return value


def nonnegative(value):
    value = money(value)
    if value < 0:
        raise ValueError("Amount must be nonnegative")
    return value


def shares(value):
    if type(value) is not int or value <= 0:
        raise ValueError("Quantity must be a positive whole share count")
    return value


@dataclass
class Position:
    symbol: str
    quantity: int
    basis_gbp: Decimal


@dataclass
class Ledger:
    """Long-only, one-position, GBP/USD accounting with explicit settlement dates.

    apply() is transactional in memory: rejected events leave all state unchanged.
    The event file is the audit/replay source; this class does not persist it.
    """
    cash: dict = field(default_factory=lambda: {"GBP": D(0), "USD": D(0)})
    unsettled: list = field(default_factory=list)
    position: Position | None = None
    deposits: Decimal = D(0)
    withdrawals: Decimal = D(0)
    realised_trade_pnl: Decimal = D(0)
    funded: bool = False
    last_at: datetime | None = None
    event_ids: set = field(default_factory=set)
    last_report: dict | None = None

    def apply(self, event):
        if not isinstance(event, dict):
            raise ValueError("Event must be an object")
        payload = dict(event)
        identity = payload.pop("id")
        kind = payload.pop("type")
        at = utc(payload.pop("at"))
        if not isinstance(identity, str) or not identity or len(identity) > 128:
            raise ValueError("Invalid event id")
        if identity in self.event_ids:
            raise ValueError("Duplicate event id")
        if self.last_at is not None and at < self.last_at:
            raise ValueError("Events must be chronological")
        handlers = {"fund": "_fund", "deposit": "_deposit", "withdraw": "_withdraw",
                    "exchange": "_exchange", "buy": "_buy", "sell": "_sell",
                    "settle": "_settle", "value": "_value"}
        if kind not in handlers:
            raise ValueError("Unknown ledger event")
        if not self.funded and kind != "fund":
            raise ValueError("Initial funding must be first")
        candidate = deepcopy(self)
        candidate.last_report = None
        getattr(candidate, handlers[kind])(at=at, **payload)
        candidate.last_at = at
        candidate.event_ids.add(identity)
        self.__dict__.update(candidate.__dict__)

    def _fund(self, at, amount):
        amount = positive(amount)
        if self.funded or amount != Policy().initial_capital:
            raise ValueError("Fund exactly once with the agreed GBP initial capital")
        self.cash["GBP"] = amount
        self.funded = True

    def _flow(self, currency, amount, usd_to_gbp):
        if currency not in self.cash:
            raise ValueError("Only GBP/USD supported")
        amount = positive(amount)
        fx = positive(usd_to_gbp)
        return amount, amount * (fx if currency == "USD" else D(1))

    def _debit(self, currency, amount):
        if amount > self.cash[currency]:
            raise ValueError("Insufficient settled cash")
        self.cash[currency] -= amount

    def _deposit(self, at, currency, amount, usd_to_gbp):
        amount, gbp = self._flow(currency, amount, usd_to_gbp)
        self.cash[currency] += amount
        self.deposits += gbp

    def _withdraw(self, at, currency, amount, usd_to_gbp):
        amount, gbp = self._flow(currency, amount, usd_to_gbp)
        self._debit(currency, amount)
        self.withdrawals += gbp

    def _exchange(self, at, from_currency, amount, received, fee_gbp):
        if from_currency not in self.cash:
            raise ValueError("Only GBP/USD supported")
        target = "USD" if from_currency == "GBP" else "GBP"
        amount, received, fee = positive(amount), positive(received), nonnegative(fee_gbp)
        self._debit(from_currency, amount)
        self.cash[target] += received
        self._debit("GBP", fee)

    def _buy(self, at, symbol, quantity, price, fee_usd, usd_to_gbp):
        if not isinstance(symbol, str) or not symbol.isalnum():
            raise ValueError("Invalid symbol")
        if self.position and self.position.symbol != symbol:
            raise ValueError("Only one open symbol is supported")
        quantity = shares(quantity)
        price, fee, fx = positive(price), nonnegative(fee_usd), positive(usd_to_gbp)
        cost = quantity * price + fee
        self._debit("USD", cost)
        if self.position:
            self.position.quantity += quantity
            self.position.basis_gbp += cost * fx
        else:
            self.position = Position(symbol, quantity, cost * fx)

    def _sell(self, at, symbol, quantity, price, fee_usd, usd_to_gbp, settles_on):
        quantity = shares(quantity)
        if not self.position or self.position.symbol != symbol or quantity > self.position.quantity:
            raise ValueError("Cannot sell unowned shares")
        price, fee, fx = positive(price), nonnegative(fee_usd), positive(usd_to_gbp)
        due = date.fromisoformat(settles_on)
        if due.isoformat() != settles_on or due <= at.date():
            raise ValueError("Supply an explicit future settlement date")
        proceeds = quantity * price - fee
        if proceeds < 0:
            raise ValueError("Fees exceed sale proceeds")
        # Allocate from remaining basis so the final sale consumes every penny.
        basis = (self.position.basis_gbp if quantity == self.position.quantity else
                 min(self.position.basis_gbp, (self.position.basis_gbp * quantity /
                     self.position.quantity).quantize(D("0.00000001"))))
        self.realised_trade_pnl += proceeds * fx - basis
        self.position.quantity -= quantity
        self.position.basis_gbp -= basis
        if self.position.quantity == 0:
            self.position = None
        self.unsettled.append((due, proceeds))

    def _settle(self, at):
        remaining = []
        for due, amount in self.unsettled:
            if due <= at.date():
                self.cash["USD"] += amount
            else:
                remaining.append((due, amount))
        self.unsettled = remaining

    def _value(self, at, usd_to_gbp, prices):
        fx = positive(usd_to_gbp)
        expected = {self.position.symbol} if self.position else set()
        if not isinstance(prices, dict) or set(prices) != expected:
            raise ValueError("Supply exactly the held symbol's current price")
        market_value = D(0)
        unrealised = D(0)
        if self.position:
            market_value = self.position.quantity * positive(prices[self.position.symbol]) * fx
            unrealised = market_value - self.position.basis_gbp
        pending = sum((amount for _, amount in self.unsettled), D(0))
        equity = self.cash["GBP"] + (self.cash["USD"] + pending) * fx + market_value
        mark = Mark(equity, self.deposits, self.withdrawals)
        self.last_report = {
            "mode": "offline_accounting_only", "as_of": at.isoformat(),
            "usd_to_gbp": fx,
            "equity_gbp": equity, "deposits_gbp": self.deposits,
            "withdrawals_gbp": self.withdrawals,
            "account_pnl_gbp": mark.adjusted_equity - Policy().initial_capital,
            "realised_trade_pnl_gbp": self.realised_trade_pnl,
            "unrealised_position_pnl_gbp": unrealised,
            "settled_cash": dict(self.cash), "unsettled_usd": pending,
            "position": None if not self.position else {
                "symbol": self.position.symbol, "quantity": self.position.quantity,
                "basis_gbp": self.position.basis_gbp, "market_value_gbp": market_value},
        }


def replay_ledger(events):
    ledger = Ledger()
    for event in events:
        ledger.apply(event)
    if ledger.last_report is None:
        raise ValueError("Ledger must end with a value event")
    return ledger.last_report
