"""Causal descriptive features from completed bars; no labels or trade signals."""
from collections import deque
from copy import deepcopy
from dataclasses import dataclass, field
from decimal import Decimal as D

from .batches import completed_batches
from .calendar import session_bounds

FEATURE_SCHEMA = "completed-minute-features-v1"


@dataclass
class _SymbolState:
    closes: deque = field(default_factory=lambda: deque(maxlen=5))
    volumes: deque = field(default_factory=lambda: deque(maxlen=20))
    count: int = 0
    volume: D = D(0)
    weighted_price: D = D(0)
    opening_high: D | None = None
    opening_low: D | None = None

    def observe(self, bar):
        previous = self.closes[-1] if self.closes else None
        five_back = self.closes[0] if len(self.closes) == 5 else None
        prior_volume = sum(self.volumes, D(0)) / 20 if len(self.volumes) == 20 else None
        self.count += 1
        self.volume += bar.volume
        self.weighted_price += (bar.high + bar.low + bar.close) / 3 * bar.volume
        if self.count <= 30:
            self.opening_high = bar.high if self.opening_high is None else max(self.opening_high, bar.high)
            self.opening_low = bar.low if self.opening_low is None else min(self.opening_low, bar.low)
        self.closes.append(bar.close)
        self.volumes.append(bar.volume)
        return dict(symbol=bar.symbol, bars_seen=self.count, close=bar.close,
                    return_1m=None if previous is None else bar.close / previous - 1,
                    return_5m=None if five_back is None else bar.close / five_back - 1,
                    sma_5=None if len(self.closes) < 5 else sum(self.closes, D(0)) / 5,
                    prior_volume_mean_20=prior_volume,
                    volume_ratio_20=None if not prior_volume else bar.volume / prior_volume,
                    cumulative_volume=self.volume,
                    ohlc_vwap_proxy=None if not self.volume else self.weighted_price / self.volume,
                    opening_range_complete=self.count >= 30,
                    opening_range_high=self.opening_high if self.count >= 30 else None,
                    opening_range_low=self.opening_low if self.count >= 30 else None)


class FeatureEngine:
    """One fixed universe, complete contiguous prefixes beginning at session open.

    Input Bar objects must have passed numeric/OHLC validation. An update is atomic
    across symbols; rejected batches leave previous feature state unchanged.
    """
    def __init__(self, symbols):
        symbols = list(symbols)
        if not symbols or len(set(symbols)) != len(symbols) or any(not isinstance(s, str) or not s.isalnum() for s in symbols):
            raise ValueError("Feature symbols must be unique nonempty names")
        self.symbols = tuple(sorted(symbols))
        self._states = {}
        self._session = None
        self._last_available = None

    def update(self, batch):
        # Recheck atomic membership even if callers construct a batch directly.
        validated = completed_batches(batch.bars, self.symbols)
        if len(validated) != 1:
            raise ValueError("Feature update requires exactly one simultaneous batch")
        batch = validated[0]
        session = batch.bars[0].session
        start = batch.bars[0].start
        if self._last_available is not None and batch.available_at <= self._last_available:
            raise ValueError("Feature batches must advance in time")
        if session != self._session:
            if start != session_bounds(session)[0]:
                raise ValueError("Feature session must begin at the scheduled opening minute")
            states = {s: _SymbolState() for s in self.symbols}
        else:
            if start != self._last_available:
                raise ValueError("Feature session has a missing minute")
            states = deepcopy(self._states)
        rows = [states[bar.symbol].observe(bar) for bar in batch.bars]
        self._states, self._session, self._last_available = states, session, batch.available_at
        return dict(type="features_closed", schema=FEATURE_SCHEMA, session=session,
                    available_at=batch.available_at.isoformat(), rows=rows)


def feature_snapshots(bars, symbols):
    engine = FeatureEngine(symbols)
    return [engine.update(batch) for batch in completed_batches(bars, engine.symbols)]
