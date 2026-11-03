"""BetPlay provider (Kambi public offering API).

BetPlay Colombia is powered by Kambi. The public ``listView`` endpoint lists
the NBA events and the per-event endpoint returns every prematch market. Both
are unauthenticated GET requests; no cookie, token or signature is copied.

Kambi reports odds and lines in thousandths (``1580`` = ``1.580``,
``227500`` = ``227.5``). Only ``NOT_STARTED`` NBA events are used; live events
are discarded. A 403/429/captcha raises ``ProviderBlockedError`` and is not
retried.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime, timezone

from surebets.errors import ProviderUnavailableError
from surebets.models import OddsQuote
from surebets.net import FetchPolicy, PoliteFetcher
from surebets.normalize import canonical_market, canonical_team, selection_side
from surebets.providers.base import OddsProvider

BASE_URL = "https://us.offering-api.kambicdn.com/offering/v2018/betplay"
LIST_URL = f"{BASE_URL}/listView/all.json"
EVENT_URL = f"{BASE_URL}/betoffer/event/{{event_id}}.json"
QUERY = {
    "lang": "es_ES",
    "market": "CO",
    "client_id": "2",
    "channel_id": "1",
    "useCombined": "true",
}
PERIOD_MARKERS = (
    "1st half",
    "2nd half",
    "1st quarter",
    "2nd quarter",
    "3rd quarter",
    "4th quarter",
    "1.ª parte",
    "1.er cuarto",
    "2.º cuarto",
    "3.er cuarto",
    "4.º cuarto",
)
ONE = "OT_ONE"
TWO = "OT_TWO"
OVER = "OT_OVER"
UNDER = "OT_UNDER"


@dataclass(frozen=True)
class BetPlayEvent:
    event_id: str
    home: str
    away: str
    start_time: datetime


def _parse_time(value: str) -> datetime:
    text = value.strip()
    if text.endswith(("Z", "z")):
        text = f"{text[:-1]}+00:00"
    parsed = datetime.fromisoformat(text)
    if parsed.tzinfo is None:
        raise ProviderUnavailableError("BetPlay: event start time without timezone")
    return parsed


def _milli(value: object) -> float | None:
    if value is None or isinstance(value, bool):
        return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    if number != number:  # NaN
        return None
    return number / 1000.0


def _event_from(item: dict, now: datetime) -> BetPlayEvent | None:
    event = item.get("event", item)
    path = event.get("path") or []
    if not any(entry.get("termKey") == "nba" for entry in path):
        return None
    if event.get("state") != "NOT_STARTED":
        return None
    if event.get("nonLiveBoCount", 0) <= 0:
        return None
    try:
        start_time = _parse_time(event["start"])
    except (KeyError, ValueError) as exc:
        raise ProviderUnavailableError("BetPlay: invalid event payload") from exc
    if start_time <= now:
        return None
    return BetPlayEvent(
        event_id=str(event["id"]),
        home=event["homeName"],
        away=event["awayName"],
        start_time=start_time,
    )


def _team_total_prefix(label: str, event: BetPlayEvent) -> str | None:
    match = re.search(r"total points by (.+?)(?:\s+-|$)", label, re.IGNORECASE)
    if match is None:
        return None
    try:
        team = canonical_team(match.group(1))
    except ValueError:
        return None
    if team == canonical_team(event.home):
        return "home"
    if team == canonical_team(event.away):
        return "away"
    return None


def _selection(
    market: str,
    outcome_type: str,
    label: str,
    event: BetPlayEvent,
) -> str | None:
    if market == "moneyline" or market == "handicap":
        if outcome_type == ONE:
            return "home"
        if outcome_type == TWO:
            return "away"
        return selection_side(label, event.home, event.away)
    if market == "total" or market.startswith("player_"):
        if outcome_type == OVER:
            return "over"
        if outcome_type == UNDER:
            return "under"
        return selection_side(label, event.home, event.away)
    return None


def parse_event_offers(
    event: BetPlayEvent,
    offers: list[dict],
    captured_at: datetime,
) -> list[OddsQuote]:
    quotes: list[OddsQuote] = []
    for offer in offers:
        criterion = offer.get("criterion") or {}
        label = criterion.get("englishLabel") or ""
        short = criterion.get("shortEnglishLabel")
        if any(marker.casefold() in label.casefold() for marker in PERIOD_MARKERS):
            continue
        market = canonical_market(label, short)
        if market is None:
            continue
        team_prefix = _team_total_prefix(label, event) if market == "team_total" else None
        if market == "team_total" and team_prefix is None:
            continue
        for outcome in offer.get("outcomes") or []:
            if outcome.get("status") != "OPEN":
                continue
            odds = _milli(outcome.get("odds"))
            if odds is None or odds <= 1.0:
                continue
            line = _milli(outcome.get("line"))
            if market != "moneyline" and line is None:
                continue
            if market == "team_total":
                side = _selection("total", outcome.get("type", ""), outcome.get("label", ""), event)
                if side is None:
                    continue
                selection = f"{team_prefix}_{side}"
            else:
                side = _selection(market, outcome.get("type", ""), outcome.get("label", ""), event)
                if side is None:
                    continue
                selection = side
            player = outcome.get("participant") if market.startswith("player_") else None
            if market.startswith("player_") and not player:
                continue
            quotes.append(
                OddsQuote(
                    event_id=event.event_id,
                    home=event.home,
                    away=event.away,
                    start_time=event.start_time,
                    market=market,
                    line=line,
                    selection=selection,
                    bookmaker="BetPlay",
                    decimal_odds=odds,
                    captured_at=captured_at,
                    player=player,
                )
            )
    return quotes


def _best_quotes(quotes: list[OddsQuote]) -> list[OddsQuote]:
    best: dict[tuple, OddsQuote] = {}
    for quote in quotes:
        key = (quote.event_id, quote.market, quote.line, quote.selection, quote.player)
        current = best.get(key)
        if current is None or quote.decimal_odds > current.decimal_odds:
            best[key] = quote
    return list(best.values())


class BetPlayProvider(OddsProvider):
    """Read BetPlay NBA prematch odds from Kambi's public endpoints."""

    bookmaker = "BetPlay"

    def __init__(
        self,
        fetcher: PoliteFetcher | None = None,
        *,
        now=lambda: datetime.now(timezone.utc),
        max_events: int = 30,
    ) -> None:
        self._fetcher = fetcher or PoliteFetcher(FetchPolicy())
        self._now = now
        self.max_events = max_events

    def fetch_odds(self) -> list[OddsQuote]:
        captured_at = self._now()
        payload = self._fetcher.get_json(
            self.bookmaker, LIST_URL, QUERY, pass_start=True
        )
        events = []
        for item in payload.get("events", []):
            event = _event_from(item, captured_at)
            if event is not None:
                events.append(event)
        events = events[: self.max_events]

        quotes: list[OddsQuote] = []
        for event in events:
            detail = self._fetcher.get_json(
                self.bookmaker,
                EVENT_URL.format(event_id=event.event_id),
                QUERY,
            )
            quotes.extend(
                parse_event_offers(event, detail.get("betOffers", []), captured_at)
            )
        return _best_quotes(quotes)

