"""Tests for deterministic name normalisation."""

from __future__ import annotations

import pytest

from surebets.normalize import (
    canonical_market,
    canonical_team,
    event_signature,
    normalize_name,
    selection_side,
)


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("LAL Lakers", "los angeles lakers"),
        ("Los Angeles Lakers", "los angeles lakers"),
        ("LA Lakers", "los angeles lakers"),
        ("Cleveland Cavaliers", "cleveland cavaliers"),
        ("CLE Cavaliers", "cleveland cavaliers"),
        ("Portland Trail Blazers", "portland trail blazers"),
        ("POR Trail Blazers", "portland trail blazers"),
    ],
)
def test_canonical_team(raw: str, expected: str) -> None:
    assert canonical_team(raw) == expected


def test_canonical_team_rejects_unknown_names() -> None:
    with pytest.raises(ValueError):
        canonical_team("Seattle Supersonics")


def test_normalize_name_removes_accents_and_punctuation() -> None:
    assert normalize_name("Hándicap – Partido") == "handicap partido"
    assert normalize_name("Pérdidas de balón") == "perdidas de balon"


@pytest.mark.parametrize(
    ("label", "short", "expected"),
    [
        ("Moneyline - Including Overtime", None, "moneyline"),
        ("Línea de dinero – Partido", None, "moneyline"),
        ("Point Spread - Including Overtime", None, "handicap"),
        ("Hándicap – Partido", None, "handicap"),
        ("Total Points - Including Overtime", None, "total"),
        ("Total – Partido", None, "total"),
        ("Total Points by Oklahoma City Thunder", None, "team_total"),
        ("Anything", "Player Points", "player_points"),
        ("Anything", "Player Rebounds & Assists", "player_rebounds_assists"),
        ("Winning Margin - Including Overtime", None, None),
    ],
)
def test_canonical_market(label: str, short: str | None, expected: str | None) -> None:
    assert canonical_market(label, short) == expected


def test_event_signature_is_order_independent() -> None:
    assert event_signature("LAL Lakers", "Boston Celtics") == event_signature(
        "Boston Celtics", "los angeles lakers"
    )


@pytest.mark.parametrize(
    ("label", "expected"),
    [
        ("Over", "over"),
        ("Más de", "over"),
        ("Under", "under"),
        ("Menos de", "under"),
        ("Cleveland Cavaliers", "home"),
        ("Oklahoma City Thunder", "away"),
    ],
)
def test_selection_side(label: str, expected: str) -> None:
    home = "Cleveland Cavaliers"
    away = "Oklahoma City Thunder"
    assert selection_side(label, home, away) == expected
