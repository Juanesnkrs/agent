"""Shared odds data model."""

import math
from dataclasses import dataclass
from datetime import datetime

_TEXT_FIELDS = ("event_id", "home", "away", "market", "selection", "bookmaker")
_TIMESTAMP_FIELDS = ("start_time", "captured_at")


def _is_number(value: object) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool)


@dataclass(frozen=True, slots=True)
class OddsQuote:
    """A single prematch selection offered by one bookmaker."""

    event_id: str
    home: str
    away: str
    start_time: datetime
    market: str
    line: float | None
    selection: str
    bookmaker: str
    decimal_odds: float
    captured_at: datetime
    player: str | None = None

    def __post_init__(self) -> None:
        for field in _TEXT_FIELDS:
            value = getattr(self, field)
            if not isinstance(value, str) or not value.strip():
                raise ValueError(f"{field} must be a non-empty string")
            object.__setattr__(self, field, value.strip())

        if self.player is not None:
            if not isinstance(self.player, str) or not self.player.strip():
                raise ValueError("player must be a non-empty string when present")
            object.__setattr__(self, "player", self.player.strip())

        if not _is_number(self.decimal_odds) or not math.isfinite(self.decimal_odds):
            raise ValueError("decimal_odds must be a finite number greater than 1")
        if self.decimal_odds <= 1.0:
            raise ValueError("decimal_odds must be a finite number greater than 1")
        object.__setattr__(self, "decimal_odds", float(self.decimal_odds))

        if self.line is not None:
            if not _is_number(self.line) or not math.isfinite(self.line):
                raise ValueError("line must be finite when present")
            object.__setattr__(self, "line", float(self.line))

        for field in _TIMESTAMP_FIELDS:
            value = getattr(self, field)
            if not isinstance(value, datetime):
                raise ValueError(f"{field} must be a datetime")
            if value.tzinfo is None or value.utcoffset() is None:
                raise ValueError(f"{field} must be timezone-aware")

        if self.home.casefold() == self.away.casefold():
            raise ValueError("home and away must differ")

