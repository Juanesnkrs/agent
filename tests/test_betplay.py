"""Tests for the BetPlay (Kambi) provider, offline against saved fixtures."""

from __future__ import annotations

import copy
import json
from datetime import datetime, timezone
from pathlib import Path

import pytest

from surebets.errors import ProviderBlockedError
from surebets.providers.betplay import LIST_URL, BetPlayProvider

FIXTURES = Path(__file__).parent / "fixtures" / "betplay"
LIST_PAYLOAD = json.loads((FIXTURES / "listview.json").read_text(encoding="utf-8"))
EVENT_PAYLOAD = json.loads((FIXTURES / "event_1028754179.json").read_text(encoding="utf-8"))
NOW = datetime(2026, 11, 2, 12, 0, tzinfo=timezone.utc)


class FakeFetcher:
    def __init__(self, list_payload: object = None, event_payload: object = None) -> None:
        self.list_payload = copy.deepcopy(list_payload or LIST_PAYLOAD)
        self.event_payload = copy.deepcopy(event_payload or EVENT_PAYLOAD)
        self.calls: list[tuple[str, bool]] = []

    def get_json(self, book: str, url: str, params=None, *, pass_start: bool = False):
        self.calls.append((url, pass_start))
        assert book == "BetPlay"
        if url == LIST_URL:
            return self.list_payload
        return self.event_payload


class BlockedFetcher:
    def get_json(self, *args: object, **kwargs: object) -> object:
        raise ProviderBlockedError("BetPlay: HTTP 403")


def make_provider(fetcher: FakeFetcher | None = None) -> BetPlayProvider:
    return BetPlayProvider(fetcher=fetcher or FakeFetcher(), now=lambda: NOW)


def test_list_fetch_is_the_start_of_a_pass() -> None:
    fetcher = FakeFetcher()
    make_provider(fetcher).fetch_odds()

    assert fetcher.calls[0] == (LIST_URL, True)
    assert all(not pass_start for _, pass_start in fetcher.calls[1:])


def test_parses_moneyline() -> None:
    quotes = make_provider().fetch_odds()
    moneyline = {
        quote.selection: quote
        for quote in quotes
        if quote.market == "moneyline" and quote.event_id == "1028754179"
    }

    assert moneyline["home"].decimal_odds == pytest.approx(1.58)
    assert moneyline["away"].decimal_odds == pytest.approx(2.43)
    assert moneyline["home"].home == "Cleveland Cavaliers"
    assert moneyline["home"].away == "Oklahoma City Thunder"
    assert moneyline["home"].captured_at == NOW
    assert moneyline["home"].start_time == datetime(2026, 11, 3, 0, 0, tzinfo=timezone.utc)


def test_converts_kambi_thousandths_for_lines_and_odds() -> None:
    quotes = make_provider().fetch_odds()
    totals = [
        quote
        for quote in quotes
        if quote.event_id == "1028754179"
        and quote.market == "total"
        and quote.line == pytest.approx(227.5)
    ]
    spread = [
        quote
        for quote in quotes
        if quote.event_id == "1028754179"
        and quote.market == "handicap"
        and quote.line == -6.5
    ]

    assert {quote.selection for quote in totals} == {"over", "under"}
    assert sorted(quote.decimal_odds for quote in totals) == [pytest.approx(1.81), pytest.approx(2.02)]
    assert [(quote.selection, quote.decimal_odds) for quote in spread] == [("home", 2.25)]


def test_team_total_uses_the_named_team() -> None:
    quotes = make_provider().fetch_odds()
    okc = [
        quote
        for quote in quotes
        if quote.market == "team_total" and quote.selection.startswith("away_")
    ]

    assert {quote.selection for quote in okc} == {"away_over", "away_under"}
    assert [quote.line for quote in okc] == [pytest.approx(111.5), pytest.approx(111.5)]


def test_player_prop_keeps_the_player_name() -> None:
    quotes = make_provider().fetch_odds()
    mccain = [
        quote
        for quote in quotes
        if quote.event_id == "1028754179" and quote.player == "Jared McCain"
    ]

    assert {quote.market for quote in mccain} == {"player_points"}
    assert {quote.selection for quote in mccain} == {"over", "under"}
    assert [quote.line for quote in mccain] == [pytest.approx(13.5), pytest.approx(13.5)]


def test_ignores_non_nba_and_live_events() -> None:
    payload = copy.deepcopy(LIST_PAYLOAD)
    payload["events"][0]["event"]["state"] = "STARTED"
    non_nba = copy.deepcopy(payload["events"][1])
    non_nba["event"]["path"] = [
        {"termKey": "football", "name": "Fútbol", "englishName": "Football"}
    ]
    payload["events"].append(non_nba)
    fetcher = FakeFetcher(list_payload=payload)
    provider = make_provider(fetcher)

    quotes = provider.fetch_odds()

    detail_calls = [url for url, _ in fetcher.calls if url != LIST_URL]
    assert len(detail_calls) == len(payload["events"]) - 2
    assert all(quote.event_id != payload["events"][0]["event"]["id"] for quote in quotes)


def test_deduplicates_same_selection_keeping_best_odds() -> None:
    payload = copy.deepcopy(EVENT_PAYLOAD)
    duplicated = copy.deepcopy(payload["betOffers"][0])
    duplicated["id"] = 999
    duplicated["outcomes"][0]["odds"] = 1700
    payload["betOffers"].append(duplicated)
    fetcher = FakeFetcher(event_payload=payload)

    moneyline_home = [
        quote
        for quote in make_provider(fetcher).fetch_odds()
        if quote.market == "moneyline"
        and quote.selection == "home"
        and quote.event_id == "1028754179"
    ]

    assert len(moneyline_home) == 1
    assert moneyline_home[0].decimal_odds == pytest.approx(1.70)


def test_block_propagates_without_detail_requests() -> None:
    with pytest.raises(ProviderBlockedError):
        BetPlayProvider(fetcher=BlockedFetcher(), now=lambda: NOW).fetch_odds()
