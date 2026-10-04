"""Atomic completed-bar batches for a declared symbol set; no fills or ranking."""
from dataclasses import dataclass
from itertools import groupby

from .calendar import validate_minute


@dataclass(frozen=True)
class CompletedBatch:
    bars: tuple

    @property
    def available_at(self):
        return self.bars[0].available_at

    def event(self):
        return {"type": "bar_batch_closed", "available_at": self.available_at.isoformat(),
                "session": self.bars[0].session, "bars": [bar.event() for bar in self.bars]}


def completed_batches(bars, symbols):
    """Validate the entire stream before returning canonical simultaneous batches.

    Every observed timestamp must contain every declared symbol exactly once.
    Whole missing timestamps require a separate calendar coverage check.
    """
    symbols, bars = list(symbols), list(bars)
    if (not symbols or len(symbols) != len(set(symbols)) or
            any(not isinstance(s, str) or not s.isalnum() for s in symbols)):
        raise ValueError("Batch symbols must be unique nonempty symbol names")
    times = [bar.available_at for bar in bars]
    if not bars or times != sorted(times):
        raise ValueError("Batch bars must be nonempty and chronological")
    result = []
    for _, group in groupby(bars, key=lambda b: b.available_at):
        frame = tuple(sorted(group, key=lambda b: b.symbol))
        if [bar.symbol for bar in frame] != sorted(symbols):
            raise ValueError("Every completed batch requires each declared symbol exactly once")
        for bar in frame:
            validate_minute(bar.start, bar.session)
        result.append(CompletedBatch(frame))
    return result
