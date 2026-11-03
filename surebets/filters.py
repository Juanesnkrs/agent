"""Prematch and freshness filters applied before any comparison."""

from __future__ import annotations

from datetime import datetime, timedelta

from surebets.models import OddsQuote


def prematch_filter(
    quotes: list[OddsQuote],
    now: datetime,
    min_minutes: float = 30,
    max_age_minutes: float = 10,
) -> tuple[list[OddsQuote], dict[str, int]]:
    """Keep quotes for events starting in at least ``min_minutes`` and fresh enough."""
    kept: list[OddsQuote] = []
    stats = {"too_close_or_started": 0, "stale": 0}
    for q in quotes:
        if q.start_time - now < timedelta(minutes=min_minutes):
            stats["too_close_or_started"] += 1
        elif now - q.captured_at > timedelta(minutes=max_age_minutes):
            stats["stale"] += 1
        else:
            kept.append(q)
    return kept, stats
