"""Manual CSV odds provider."""

from __future__ import annotations

import csv
import math
from datetime import datetime
from pathlib import Path

from surebets.errors import ProviderError
from surebets.models import OddsQuote
from surebets.providers.base import OddsProvider

DEFAULT_MANUAL_PATH = Path("data/manual_odds.csv")
REQUIRED_COLUMNS = (
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
)


class ManualProvider(OddsProvider):
    """Read odds from a user-maintained CSV file."""

    def __init__(self, path: str | Path | None = None) -> None:
        self.path = Path(path) if path is not None else DEFAULT_MANUAL_PATH

    def fetch_odds(self) -> list[OddsQuote]:
        try:
            with self.path.open(encoding="utf-8-sig", newline="") as handle:
                reader = csv.DictReader(handle)
                if reader.fieldnames is None:
                    raise ProviderError(f"{self.path}: CSV file is empty")

                missing = [column for column in REQUIRED_COLUMNS if column not in reader.fieldnames]
                if missing:
                    joined = ", ".join(missing)
                    raise ProviderError(f"{self.path}: missing required columns: {joined}")

                return [self._parse_row(row, reader.line_num) for row in reader]
        except OSError as exc:
            raise ProviderError(f"manual odds file not found or unreadable: {self.path}") from exc

    def _parse_row(self, row: dict[str, str | None], line_number: int) -> OddsQuote:
        raw_line = (row.get("line") or "").strip()
        line = None if not raw_line else _parse_float(raw_line, "line", line_number)

        try:
            return OddsQuote(
                event_id=_required_text(row, "event_id", line_number),
                home=_required_text(row, "home", line_number),
                away=_required_text(row, "away", line_number),
                start_time=_parse_datetime(
                    _required_text(row, "start_time", line_number),
                    "start_time",
                    line_number,
                ),
                market=_required_text(row, "market", line_number),
                line=line,
                selection=_required_text(row, "selection", line_number),
                bookmaker=_required_text(row, "bookmaker", line_number),
                decimal_odds=_parse_odds(
                    _required_text(row, "decimal_odds", line_number),
                    line_number,
                ),
                captured_at=_parse_datetime(
                    _required_text(row, "captured_at", line_number),
                    "captured_at",
                    line_number,
                ),
            )
        except ValueError as exc:
            raise ProviderError(f"row {line_number}: {exc}") from exc


def _required_text(row: dict[str, str | None], field: str, line_number: int) -> str:
    value = row.get(field)
    if value is None or not value.strip():
        raise ProviderError(f"row {line_number}: {field} is required")
    return value.strip()


def _parse_float(value: str, field: str, line_number: int) -> float:
    try:
        number = float(value)
    except ValueError as exc:
        raise ProviderError(f"row {line_number}: {field} must be numeric") from exc
    if not math.isfinite(number):
        raise ProviderError(f"row {line_number}: {field} must be finite")
    return number


def _parse_odds(value: str, line_number: int) -> float:
    odds = _parse_float(value, "decimal_odds", line_number)
    if odds <= 1.0:
        raise ProviderError(f"row {line_number}: decimal_odds must be greater than 1")
    return odds


def _parse_datetime(value: str, field: str, line_number: int) -> datetime:
    text = value.strip()
    if text.endswith(("Z", "z")):
        text = f"{text[:-1]}+00:00"
    try:
        result = datetime.fromisoformat(text)
    except ValueError as exc:
        raise ProviderError(f"row {line_number}: {field} must be ISO 8601") from exc
    if result.tzinfo is None or result.utcoffset() is None:
        raise ProviderError(f"row {line_number}: {field} must be timezone-aware")
    return result

