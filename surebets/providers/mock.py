"""Deterministic mock odds provider."""

from __future__ import annotations

from collections.abc import Iterable
from datetime import datetime, timezone

from surebets.models import OddsQuote
from surebets.providers.base import OddsProvider


def _quote(
    *,
    market: str,
    line: float | None,
    selection: str,
    bookmaker: str,
    decimal_odds: float,
) -> OddsQuote:
    return OddsQuote(
        event_id="mock-nba-001",
        home="Los Angeles Lakers",
        away="Boston Celtics",
        start_time=datetime(2026, 11, 3, 0, 30, tzinfo=timezone.utc),
        market=market,
        line=line,
        selection=selection,
        bookmaker=bookmaker,
        decimal_odds=decimal_odds,
        captured_at=datetime(2026, 11, 2, 18, 0, tzinfo=timezone.utc),
    )


DEFAULT_MOCK_QUOTES = (
    _quote(
        market="moneyline",
        line=None,
        selection="home",
        bookmaker="MockBook A",
        decimal_odds=2.10,
    ),
    _quote(
        market="moneyline",
        line=None,
        selection="away",
        bookmaker="MockBook B",
        decimal_odds=2.15,
    ),
    _quote(
        market="total",
        line=220.5,
        selection="over",
        bookmaker="MockBook A",
        decimal_odds=1.95,
    ),
    _quote(
        market="total",
        line=220.5,
        selection="under",
        bookmaker="MockBook B",
        decimal_odds=2.05,
    ),
    _quote(
        market="handicap",
        line=-4.5,
        selection="home",
        bookmaker="MockBook A",
        decimal_odds=1.91,
    ),
    _quote(
        market="handicap",
        line=4.5,
        selection="away",
        bookmaker="MockBook B",
        decimal_odds=2.00,
    ),
)


class MockProvider(OddsProvider):
    """Return deterministic sample quotes, never network data."""

    def __init__(self, quotes: Iterable[OddsQuote] | None = None) -> None:
        self._quotes = tuple(quotes) if quotes is not None else DEFAULT_MOCK_QUOTES

    def fetch_odds(self) -> list[OddsQuote]:
        return list(self._quotes)

