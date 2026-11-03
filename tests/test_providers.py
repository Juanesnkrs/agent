"""Tests for the provider interface and local providers."""

from __future__ import annotations

import csv
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from surebets.errors import ProviderError
from surebets.models import OddsQuote
from surebets.providers.base import OddsProvider
from surebets.providers.manual import DEFAULT_MANUAL_PATH, ManualProvider
from surebets.providers.mock import MockProvider

FIXTURES = Path(__file__).parent / "fixtures"
CSV_COLUMNS = [
    "event_id",
    "home",
    "away",
    "start_time",
    "market",
    "line",
    "selection",
    "bookmaker",
    "decimal_odds",
    "captured_at",
]
BASE_ROW = {
    "event_id": "nba-2026-11-03-lal-bos",
    "home": "Los Angeles Lakers",
    "away": "Boston Celtics",
    "start_time": "2026-11-03T00:30:00Z",
    "market": "moneyline",
    "line": "",
    "selection": "home",
    "bookmaker": "Book A",
    "decimal_odds": "2.10",
    "captured_at": "2026-11-02T18:00:00Z",
}


def write_csv(
    path: Path,
    rows: list[dict[str, str]],
    columns: list[str] | None = None,
) -> Path:
    fields = columns if columns is not None else CSV_COLUMNS
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)
    return path


def make_row(**overrides: str) -> dict[str, str]:
    row = dict(BASE_ROW)
    row.update(overrides)
    return row


def make_quote(**overrides: object) -> OddsQuote:
    values: dict[str, object] = {
        "event_id": "mock-event",
        "home": "Home",
        "away": "Away",
        "start_time": datetime(2026, 11, 3, 0, 30, tzinfo=timezone.utc),
        "market": "moneyline",
        "line": None,
        "selection": "home",
        "bookmaker": "MockBook",
        "decimal_odds": 2.0,
        "captured_at": datetime(2026, 11, 2, 18, 0, tzinfo=timezone.utc),
    }
    values.update(overrides)
    return OddsQuote(**values)  # type: ignore[arg-type]


def test_manual_provider_reads_the_fixture() -> None:
    quotes = ManualProvider(FIXTURES / "manual_odds.csv").fetch_odds()

    assert len(quotes) == 6
    assert quotes[0].event_id == "nba-2026-11-03-lal-bos"
    assert quotes[0].home == "Los Angeles Lakers"
    assert quotes[0].away == "Boston Celtics"
    assert quotes[0].start_time == datetime(2026, 11, 3, 0, 30, tzinfo=timezone.utc)
    assert quotes[0].captured_at == datetime(2026, 11, 2, 18, 0, tzinfo=timezone.utc)
    assert quotes[0].market == "moneyline"
    assert quotes[0].line is None
    assert quotes[0].selection == "home"
    assert quotes[0].bookmaker == "Book A"
    assert quotes[0].decimal_odds == pytest.approx(2.10)


def test_manual_provider_parses_total_and_handicap_lines() -> None:
    quotes = ManualProvider(FIXTURES / "manual_odds.csv").fetch_odds()

    assert quotes[2].line == pytest.approx(220.5)
    assert quotes[4].line == pytest.approx(-4.5)


def test_manual_provider_uses_the_documented_default_path() -> None:
    assert DEFAULT_MANUAL_PATH == Path("data/manual_odds.csv")
    assert ManualProvider().path == DEFAULT_MANUAL_PATH


def test_manual_provider_is_an_odds_provider() -> None:
    assert isinstance(ManualProvider(FIXTURES / "manual_odds.csv"), OddsProvider)


def test_manual_provider_reports_a_missing_file(tmp_path: Path) -> None:
    with pytest.raises(ProviderError, match="not found"):
        ManualProvider(tmp_path / "missing.csv").fetch_odds()


def test_manual_provider_rejects_an_empty_file(tmp_path: Path) -> None:
    path = tmp_path / "empty.csv"
    path.write_text("", encoding="utf-8")

    with pytest.raises(ProviderError, match="empty"):
        ManualProvider(path).fetch_odds()


def test_manual_provider_accepts_a_header_only_file(tmp_path: Path) -> None:
    path = write_csv(tmp_path / "header.csv", [])

    assert ManualProvider(path).fetch_odds() == []


def test_manual_provider_rejects_a_missing_column(tmp_path: Path) -> None:
    columns = [column for column in CSV_COLUMNS if column != "captured_at"]
    path = write_csv(tmp_path / "missing-column.csv", [make_row()], columns)

    with pytest.raises(ProviderError, match="captured_at"):
        ManualProvider(path).fetch_odds()


@pytest.mark.parametrize(
    "field",
    [
        "event_id",
        "home",
        "away",
        "start_time",
        "market",
        "selection",
        "bookmaker",
        "decimal_odds",
        "captured_at",
    ],
)
def test_manual_provider_rejects_an_empty_required_value(tmp_path: Path, field: str) -> None:
    path = write_csv(tmp_path / "empty-field.csv", [make_row(**{field: ""})])

    with pytest.raises(ProviderError, match=field):
        ManualProvider(path).fetch_odds()


@pytest.mark.parametrize("value", ["1.0", "0.5", "nan", "inf", "-inf", "not-a-number"])
def test_manual_provider_rejects_invalid_decimal_odds(tmp_path: Path, value: str) -> None:
    path = write_csv(tmp_path / "invalid-odds.csv", [make_row(decimal_odds=value)])

    with pytest.raises(ProviderError, match="decimal_odds"):
        ManualProvider(path).fetch_odds()


@pytest.mark.parametrize("value", ["nan", "inf", "-inf", "not-a-number"])
def test_manual_provider_rejects_invalid_lines(tmp_path: Path, value: str) -> None:
    path = write_csv(tmp_path / "invalid-line.csv", [make_row(line=value)])

    with pytest.raises(ProviderError, match="line"):
        ManualProvider(path).fetch_odds()


def test_manual_provider_rejects_a_naive_start_time(tmp_path: Path) -> None:
    path = write_csv(
        tmp_path / "naive-start.csv",
        [make_row(start_time="2026-11-03T00:30:00")],
    )

    with pytest.raises(ProviderError, match="timezone"):
        ManualProvider(path).fetch_odds()


def test_manual_provider_rejects_a_naive_captured_at(tmp_path: Path) -> None:
    path = write_csv(
        tmp_path / "naive-captured.csv",
        [make_row(captured_at="2026-11-02T18:00:00")],
    )

    with pytest.raises(ProviderError, match="timezone"):
        ManualProvider(path).fetch_odds()


def test_manual_provider_rejects_an_invalid_start_time(tmp_path: Path) -> None:
    path = write_csv(
        tmp_path / "invalid-start.csv",
        [make_row(start_time="not-a-date")],
    )

    with pytest.raises(ProviderError, match="start_time"):
        ManualProvider(path).fetch_odds()


def test_manual_provider_accepts_offset_timestamps(tmp_path: Path) -> None:
    path = write_csv(
        tmp_path / "offset.csv",
        [make_row(start_time="2026-11-03T00:30:00-05:00")],
    )

    quote = ManualProvider(path).fetch_odds()[0]

    assert quote.start_time.utcoffset() == timedelta(hours=-5)


def test_manual_provider_ignores_extra_columns(tmp_path: Path) -> None:
    columns = [*CSV_COLUMNS, "note"]
    path = write_csv(tmp_path / "extra.csv", [make_row(note="ignored")], columns)

    quotes = ManualProvider(path).fetch_odds()

    assert len(quotes) == 1
    assert quotes[0].bookmaker == "Book A"


def test_mock_provider_returns_sample_quotes() -> None:
    quotes = MockProvider().fetch_odds()

    assert len(quotes) == 6
    assert {quote.bookmaker for quote in quotes} == {"MockBook A", "MockBook B"}
    assert {quote.event_id for quote in quotes} == {"mock-nba-001"}
    assert all(isinstance(quote, OddsQuote) for quote in quotes)
    assert all(quote.start_time.tzinfo is not None for quote in quotes)
    assert all(quote.captured_at.tzinfo is not None for quote in quotes)


def test_mock_provider_returns_a_fresh_list() -> None:
    provider = MockProvider()

    first = provider.fetch_odds()
    first.clear()

    assert len(provider.fetch_odds()) == 6


def test_mock_provider_accepts_custom_quotes() -> None:
    quote = make_quote()

    assert MockProvider([quote]).fetch_odds() == [quote]


def test_odds_provider_cannot_be_instantiated() -> None:
    with pytest.raises(TypeError):
        OddsProvider()  # type: ignore[abstract]
