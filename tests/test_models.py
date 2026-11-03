"""Tests for the immutable odds quote model."""

from datetime import datetime, timezone

import pytest

from surebets.models import OddsQuote


def make_quote(**overrides: object) -> OddsQuote:
    values: dict[str, object] = {
        "event_id": "nba-2026-11-03-lal-bos",
        "home": "Los Angeles Lakers",
        "away": "Boston Celtics",
        "start_time": datetime(2026, 11, 3, 0, 30, tzinfo=timezone.utc),
        "market": "moneyline",
        "line": None,
        "selection": "home",
        "bookmaker": "Book A",
        "decimal_odds": 2.10,
        "captured_at": datetime(2026, 11, 2, 18, 0, tzinfo=timezone.utc),
    }
    values.update(overrides)
    return OddsQuote(**values)  # type: ignore[arg-type]


def test_valid_quote_keeps_all_fields() -> None:
    quote = make_quote()

    assert quote.event_id == "nba-2026-11-03-lal-bos"
    assert quote.home == "Los Angeles Lakers"
    assert quote.away == "Boston Celtics"
    assert quote.market == "moneyline"
    assert quote.line is None
    assert quote.selection == "home"
    assert quote.bookmaker == "Book A"
    assert quote.decimal_odds == pytest.approx(2.10)
    assert quote.start_time.tzinfo is not None
    assert quote.captured_at.tzinfo is not None


def test_line_is_kept_as_float_when_present() -> None:
    quote = make_quote(line=-4)

    assert quote.line == -4.0
    assert isinstance(quote.line, float)


@pytest.mark.parametrize("value", [1.0, 0.99, -2.0, 0.0])
def test_decimal_odds_must_be_greater_than_one(value: float) -> None:
    with pytest.raises(ValueError, match="decimal_odds"):
        make_quote(decimal_odds=value)


@pytest.mark.parametrize("value", [float("nan"), float("inf"), float("-inf")])
def test_decimal_odds_must_be_finite(value: float) -> None:
    with pytest.raises(ValueError, match="decimal_odds"):
        make_quote(decimal_odds=value)


@pytest.mark.parametrize("value", [True, "2.10", None])
def test_decimal_odds_must_be_numeric(value: object) -> None:
    with pytest.raises(ValueError, match="decimal_odds"):
        make_quote(decimal_odds=value)


@pytest.mark.parametrize("value", [float("nan"), float("inf"), float("-inf")])
def test_line_must_be_finite_when_present(value: float) -> None:
    with pytest.raises(ValueError, match="line"):
        make_quote(line=value)


@pytest.mark.parametrize("value", ["4.5", True])
def test_line_must_be_numeric_when_present(value: object) -> None:
    with pytest.raises(ValueError, match="line"):
        make_quote(line=value)


@pytest.mark.parametrize(
    "field",
    ["event_id", "home", "away", "market", "selection", "bookmaker"],
)
@pytest.mark.parametrize("value", ["", "   ", None])
def test_required_text_fields_cannot_be_empty(field: str, value: object) -> None:
    with pytest.raises(ValueError, match=field):
        make_quote(**{field: value})


@pytest.mark.parametrize("field", ["start_time", "captured_at"])
def test_timestamps_must_be_timezone_aware(field: str) -> None:
    with pytest.raises(ValueError, match="timezone-aware"):
        make_quote(**{field: datetime(2026, 11, 3, 0, 30)})


@pytest.mark.parametrize("field", ["start_time", "captured_at"])
def test_timestamps_must_be_datetimes(field: str) -> None:
    with pytest.raises(ValueError, match=field):
        make_quote(**{field: "2026-11-03T00:30:00Z"})


def test_home_and_away_must_differ() -> None:
    with pytest.raises(ValueError, match="home and away"):
        make_quote(away="Los Angeles Lakers")
