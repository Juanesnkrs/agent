"""Pinnacle provider.

The pure text parsing is ported from ``nba-surebets`` (commit ``4e90b26``,
``surebets/books/pinnacle/parsing.py``). The browser navigation is isolated in
``SeleniumPinnacleSource`` because the original hard-coded a Linux chromedriver
and because ``pinnacle.com`` could not be reached from the build network
(``ERR_CONNECTION_RESET``); see ``reports/scrapers-asis.md``.

The provider only reads the public prematch page. It never logs in, never
places bets and never tries to evade a block: a captcha or a 403/429 raises
``ProviderBlockedError`` and the caller must stop using Pinnacle.
"""

from __future__ import annotations

import math
import os
import re
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Protocol

from surebets.errors import ProviderBlockedError, ProviderUnavailableError
from surebets.models import OddsQuote
from surebets.normalize import canonical_market, normalize_name, selection_side
from surebets.providers.base import OddsProvider

NBA_URL = "https://www.pinnacle.com/es/basketball/nba/matchups"
PERIOD_MARKERS = (
    "1.ª parte",
    "1.er cuarto",
    "2.º cuarto",
    "1st half",
    "1st quarter",
    "2nd quarter",
)
BLOCK_MARKERS = ("captcha", "unusual traffic", "access denied", "are you a robot")


@dataclass(frozen=True)
class PinnacleGame:
    event_id: str
    home: str
    away: str
    start_time: datetime
    url: str


@dataclass(frozen=True)
class PinnacleBlock:
    game: PinnacleGame
    label: str
    lines: tuple[str, ...]


@dataclass(frozen=True)
class PinnacleLeg:
    market: str
    selection: str
    line: float | None
    decimal_odds: float
    player: str | None = None


class PinnacleSource(Protocol):
    def load_games(self) -> list[PinnacleGame]:
        """Return the prematch NBA games listed on the public page."""

    def load_blocks(self, game: PinnacleGame) -> list[PinnacleBlock]:
        """Return the raw text blocks of every market for ``game``."""


def _clean(value: str) -> str:
    return value.strip()


def _is_blank(value: str) -> bool:
    return not value.strip()


def parse_number(value: str) -> float | None:
    """Parse ``1.91``, ``+1.5`` or ``Línea 227.5`` into a float."""
    match = re.search(r"[-+]?\d+(?:[.,]\d+)?", value)
    if match is None:
        return None
    try:
        number = float(match.group(0).replace(",", "."))
    except ValueError:
        return None
    if not math.isfinite(number):
        return None
    return number


def _pairs(body: list[str]) -> list[tuple[str, str]]:
    result = []
    for index in range(0, len(body) - 1, 2):
        left, right = body[index], body[index + 1]
        if _is_blank(left) or _is_blank(right):
            continue
        result.append((left, right))
    return result


def _chunks(body: list[str], size: int) -> list[list[str]]:
    return [body[index : index + size] for index in range(0, len(body), size)]


def _body(lines: list[str]) -> list[str]:
    """Skip a leading control line such as "Ocultar todo" when present."""
    if len(lines) > 1:
        normalized = normalize_name(lines[1])
        if not lines[1].strip() or normalized in ("ocultar todo", "hide all", "show all"):
            return lines[2:]
    return lines[1:]


def parse_block(block: PinnacleBlock) -> list[PinnacleLeg]:
    """Convert one Pinnacle market text block into legs.

    The line layouts mirror the original parser: moneyline is read as
    ``(team, odds)`` pairs, handicap and team totals as groups of four
    (line, odds, opposite line, opposite odds), totals as
    (line, over, blank, under) and player props as
    (player (stat), line, over, blank, under).
    """
    if any(marker.casefold() in block.label.casefold() for marker in PERIOD_MARKERS):
        return []

    market = canonical_market(block.label)
    if market is None:
        return []

    lines = list(block.lines)
    if not lines or normalize_name(lines[0]) != normalize_name(block.label):
        lines.insert(0, block.label)

    if market == "moneyline":
        return _parse_moneyline(block.game, lines)
    if market == "handicap":
        return _parse_handicap(block.game, lines)
    if market == "total":
        return _parse_total(lines)
    if market == "team_total":
        return _parse_team_total(block.game, lines)
    if market.startswith("player_"):
        return _parse_player(lines[1:], market)
    return []


def _parse_moneyline(game: PinnacleGame, lines: list[str]) -> list[PinnacleLeg]:
    legs = []
    for team, raw_odds in _pairs(_body(lines)):
        side = selection_side(team, game.home, game.away)
        odds = parse_number(raw_odds)
        if side is None or odds is None or odds <= 1.0:
            continue
        legs.append(PinnacleLeg("moneyline", side, None, odds))
    return legs


def _parse_handicap(game: PinnacleGame, lines: list[str]) -> list[PinnacleLeg]:
    legs = []
    for chunk in _chunks(_body(lines), 4):
        if len(chunk) < 4:
            continue
        home_line = parse_number(chunk[0])
        home_odds = parse_number(chunk[1])
        away_line = parse_number(chunk[2])
        away_odds = parse_number(chunk[3])
        if home_line is not None and home_odds is not None and home_odds > 1.0:
            legs.append(PinnacleLeg("handicap", "home", home_line, home_odds))
        if away_line is not None and away_odds is not None and away_odds > 1.0:
            legs.append(PinnacleLeg("handicap", "away", away_line, away_odds))
    return legs


def _parse_total(lines: list[str]) -> list[PinnacleLeg]:
    legs = []
    for chunk in _chunks(lines[1:], 4):
        if len(chunk) < 4:
            continue
        line = parse_number(chunk[0])
        over = parse_number(chunk[1])
        under = parse_number(chunk[3])
        if line is None:
            continue
        if over is not None and over > 1.0:
            legs.append(PinnacleLeg("total", "over", line, over))
        if under is not None and under > 1.0:
            legs.append(PinnacleLeg("total", "under", line, under))
    return legs


def _parse_team_total(game: PinnacleGame, lines: list[str]) -> list[PinnacleLeg]:
    legs = []
    teams = (("home", game.home), ("away", game.away))
    for index, chunk in enumerate(_chunks(_body(lines), 4)):
        if len(chunk) < 4 or index >= len(teams):
            continue
        prefix, _ = teams[index]
        line = parse_number(chunk[0])
        over = parse_number(chunk[1])
        under = parse_number(chunk[3])
        if line is None:
            continue
        if over is not None and over > 1.0:
            legs.append(PinnacleLeg("team_total", f"{prefix}_over", line, over))
        if under is not None and under > 1.0:
            legs.append(PinnacleLeg("team_total", f"{prefix}_under", line, under))
    return legs


def _parse_player(lines: list[str], market: str) -> list[PinnacleLeg]:
    if not lines:
        return []
    first = lines[0]
    player = first.split("(", 1)[0].strip()
    line_index = 1 if "(" in first else 0
    line = parse_number(lines[line_index]) if len(lines) > line_index else None
    over_index = line_index + 1
    under_index = line_index + 3
    over = parse_number(lines[over_index]) if len(lines) > over_index else None
    under = parse_number(lines[under_index]) if len(lines) > under_index else None
    if line is None or not player:
        return []
    legs = []
    if over is not None and over > 1.0:
        legs.append(PinnacleLeg(market, "over", line, over, player))
    if under is not None and under > 1.0:
        legs.append(PinnacleLeg(market, "under", line, under, player))
    return legs


class PinnacleProvider(OddsProvider):
    """Read Pinnacle NBA prematch odds through a source."""

    bookmaker = "Pinnacle"

    def __init__(
        self,
        source: PinnacleSource | None = None,
        *,
        now=lambda: datetime.now(timezone.utc),
    ) -> None:
        self._source = source if source is not None else SeleniumPinnacleSource()
        self._now = now

    def fetch_odds(self) -> list[OddsQuote]:
        captured_at = self._now()
        quotes: list[OddsQuote] = []
        for game in self._source.load_games():
            for block in self._source.load_blocks(game):
                for leg in parse_block(block):
                    quotes.append(
                        OddsQuote(
                            event_id=game.event_id,
                            home=game.home,
                            away=game.away,
                            start_time=game.start_time,
                            market=leg.market,
                            line=leg.line,
                            selection=leg.selection,
                            bookmaker=self.bookmaker,
                            decimal_odds=leg.decimal_odds,
                            captured_at=captured_at,
                            player=leg.player,
                        )
                    )
        return quotes


class SeleniumPinnacleSource:
    """Best-effort public-page source adapted from the original scraper.

    The original hard-coded ``src/execs/chromedriver-linux64/chromedriver`` and
    read hashed CSS-module class names; this version uses the driver configured
    by ``CHROMEDRIVER_PATH``/``PINNACLE_CHROMEDRIVER_PATH`` and raises a clear
    error instead of silently returning an empty frame.
    """

    def __init__(self, *, timeout_seconds: int = 25, headless: bool = True) -> None:
        self.timeout_seconds = timeout_seconds
        self.headless = headless

    def load_games(self) -> list[PinnacleGame]:
        driver = self._driver()
        try:
            driver.get(NBA_URL)
            self._reject_block(driver.page_source)
            deadline = time.monotonic() + self.timeout_seconds
            links = []
            while time.monotonic() < deadline:
                links = driver.find_elements(
                    "xpath", "//a[starts-with(@href, '/es/basketball/nba/')]"
                )
                if links:
                    break
                time.sleep(1)
            games: dict[str, PinnacleGame] = {}
            for link in links:
                parsed = self._game_from_link(link)
                if parsed is not None:
                    games[parsed.event_id] = parsed
            if not games:
                raise ProviderUnavailableError(
                    "Pinnacle: no NBA games found (page layout changed or no games listed)"
                )
            return list(games.values())
        finally:
            driver.quit()

    def load_blocks(self, game: PinnacleGame) -> list[PinnacleBlock]:
        driver = self._driver()
        try:
            driver.get(game.url)
            self._reject_block(driver.page_source)
            blocks: list[PinnacleBlock] = []
            selector = ".marketGroup, [data-test-id*='market']"
            for element in driver.find_elements("css selector", selector):
                text = element.text.strip()
                if not text:
                    continue
                lines = tuple(text.splitlines())
                blocks.append(PinnacleBlock(game, lines[0], lines))
            return blocks
        finally:
            driver.quit()

    def _driver(self):
        try:
            from selenium import webdriver
            from selenium.webdriver.chrome.service import Service
        except ImportError as exc:
            raise ProviderUnavailableError(
                "Pinnacle: selenium is not installed (pip install selenium)"
            ) from exc
        path = os.getenv("PINNACLE_CHROMEDRIVER_PATH") or os.getenv("CHROMEDRIVER_PATH")
        if not path:
            raise ProviderUnavailableError(
                "Pinnacle: set PINNACLE_CHROMEDRIVER_PATH (or CHROMEDRIVER_PATH) "
                "to a chromedriver binary"
            )
        options = webdriver.ChromeOptions()
        options.add_argument("--no-sandbox")
        options.add_argument("--disable-dev-shm-usage")
        options.add_argument("--disable-gpu")
        if self.headless:
            options.add_argument("--headless")
        try:
            return webdriver.Chrome(service=Service(path), options=options)
        except Exception as exc:  # pragma: no cover - depends on local browser
            raise ProviderUnavailableError(f"Pinnacle: cannot start Chrome: {exc}") from exc

    def _game_from_link(self, link) -> PinnacleGame | None:  # pragma: no cover - browser only
        href = link.get_attribute("href") or ""
        match = re.search(r"/nba/([^/]+)/(\d+)$", href)
        if match is None:
            return None
        slug, event_id = match.group(1), match.group(2)
        teams = slug.split("-vs-")
        if len(teams) != 2:
            return None
        home = teams[0].replace("-", " ").strip()
        away = teams[1].replace("-", " ").strip()
        start_time = self._start_time(link)
        if start_time is None:
            raise ProviderUnavailableError(
                "Pinnacle: could not read the event start time from the page"
            )
        return PinnacleGame(event_id, home, away, start_time, href)

    @staticmethod
    def _start_time(link) -> datetime | None:  # pragma: no cover - browser only
        for attribute in ("data-start-time", "datetime"):
            value = link.get_attribute(attribute)
            if value:
                return datetime.fromisoformat(value.replace("Z", "+00:00"))
        try:
            from selenium.webdriver.common.by import By

            time_element = link.find_element(By.TAG_NAME, "time")
            value = time_element.get_attribute("datetime")
            if value:
                return datetime.fromisoformat(value.replace("Z", "+00:00"))
        except Exception:
            return None
        return None

    @staticmethod
    def _reject_block(page_source: str) -> None:  # pragma: no cover - browser only
        lowered = page_source[:20000].casefold()
        if any(marker in lowered for marker in BLOCK_MARKERS):
            raise ProviderBlockedError("Pinnacle: captcha or access denied page")

