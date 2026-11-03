"""Tests for the ported Pinnacle text parser and provider."""

from __future__ import annotations

from datetime import datetime, timezone

import pytest

from surebets.errors import ProviderBlockedError
from surebets.models import OddsQuote
from surebets.providers.pinnacle import (
    PinnacleBlock,
    PinnacleGame,
    PinnacleProvider,
    parse_block,
)

NOW = datetime(2026, 11, 2, 12, 0, tzinfo=timezone.utc)
GAME = PinnacleGame(
    event_id="1028754179",
    home="Cleveland Cavaliers",
    away="Oklahoma City Thunder",
    start_time=datetime(2026, 11, 3, 0, 0, tzinfo=timezone.utc),
    url="https://www.pinnacle.com/es/basketball/nba/cleveland-cavaliers-vs-oklahoma-city-thunder/1028754179",
)


def block(label: str, *lines: str) -> PinnacleBlock:
    return PinnacleBlock(game=GAME, label=label, lines=(label, *lines))


def test_parse_moneyline_block() -> None:
    legs = parse_block(
        block(
            "Línea de dinero – Partido",
            "Cleveland Cavaliers",
            "1.58",
            "Oklahoma City Thunder",
            "2.43",
        )
    )

    assert [(leg.selection, leg.line, leg.decimal_odds) for leg in legs] == [
        ("home", None, 1.58),
        ("away", None, 2.43),
    ]


def test_parse_handicap_block_with_two_alternate_lines() -> None:
    legs = parse_block(
        block(
            "Hándicap – Partido",
            "Ocultar todo",
            "-1.5",
            "1.91",
            "+1.5",
            "2.00",
            "-4.5",
            "2.35",
            "+4.5",
            "1.62",
        )
    )

    assert [(leg.selection, leg.line, leg.decimal_odds) for leg in legs] == [
        ("home", -1.5, 1.91),
        ("away", 1.5, 2.00),
        ("home", -4.5, 2.35),
        ("away", 4.5, 1.62),
    ]


def test_parse_total_block() -> None:
    legs = parse_block(
        block("Total – Partido", "Línea 227.5", "1.81", "", "2.02")
    )

    assert [(leg.market, leg.selection, leg.line, leg.decimal_odds) for leg in legs] == [
        ("total", "over", 227.5, 1.81),
        ("total", "under", 227.5, 2.02),
    ]


def test_parse_team_total_block() -> None:
    legs = parse_block(
        block(
            "Total del equipo – Partido",
            "Ocultar todo",
            "Línea 111.5",
            "1.75",
            "",
            "2.02",
            "Línea 108.5",
            "1.95",
            "",
            "2.05",
        )
    )

    assert [
        (leg.market, leg.selection, leg.line, leg.decimal_odds) for leg in legs
    ] == [
        ("team_total", "home_over", 111.5, 1.75),
        ("team_total", "home_under", 111.5, 2.02),
        ("team_total", "away_over", 108.5, 1.95),
        ("team_total", "away_under", 108.5, 2.05),
    ]


def test_parse_player_block() -> None:
    legs = parse_block(
        block(
            "Puntos anotados por el jugador",
            "Jared McCain (Puntos)",
            "Línea 13.5",
            "1.78",
            "",
            "1.97",
        )
    )

    assert [(leg.market, leg.selection, leg.player, leg.line) for leg in legs] == [
        ("player_points", "over", "Jared McCain", 13.5),
        ("player_points", "under", "Jared McCain", 13.5),
    ]


def test_unknown_market_is_ignored() -> None:
    assert parse_block(block("Winning Margin", "1", "2.5", "2", "4.6")) == []


class FakeSource:
    def __init__(self, blocks: list[PinnacleBlock]) -> None:
        self._blocks = blocks
        self.games_called = 0

    def load_games(self) -> list[PinnacleGame]:
        self.games_called += 1
        return [GAME]

    def load_blocks(self, game: PinnacleGame) -> list[PinnacleBlock]:
        assert game == GAME
        return self._blocks


class FailingSource:
    def load_games(self) -> list[PinnacleGame]:
        raise ProviderBlockedError("Pinnacle: HTTP 403")

    def load_blocks(self, game: PinnacleGame) -> list[PinnacleBlock]:
        raise AssertionError("should not be called")


def test_provider_builds_quotes_with_timestamps() -> None:
    source = FakeSource(
        [
            block(
                "Línea de dinero – Partido",
                "Cleveland Cavaliers",
                "1.58",
                "Oklahoma City Thunder",
                "2.43",
            )
        ]
    )
    provider = PinnacleProvider(source=source, now=lambda: NOW)

    quotes = provider.fetch_odds()

    assert len(quotes) == 2
    assert all(isinstance(quote, OddsQuote) for quote in quotes)
    assert {quote.bookmaker for quote in quotes} == {"Pinnacle"}
    assert {quote.selection for quote in quotes} == {"home", "away"}
    assert all(quote.captured_at == NOW for quote in quotes)
    assert all(quote.start_time == GAME.start_time for quote in quotes)


def test_provider_propagates_block_without_retrying() -> None:
    provider = PinnacleProvider(source=FailingSource(), now=lambda: NOW)

    with pytest.raises(ProviderBlockedError):
        provider.fetch_odds()
