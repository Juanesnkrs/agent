"""Deterministic names for teams, markets and selections.

Bookmakers spell the same thing differently ("LAL Lakers", "Los Angeles
Lakers", "Hándicap", "Point Spread"). Everything that enters the detector is
reduced to a small canonical vocabulary here. Fuzzy matching is intentionally
not used: when two names cannot be normalised deterministically the row is
skipped and reported.
"""

from __future__ import annotations

import re
import unicodedata
from typing import Any, Dict

# Full and abbreviated NBA names seen in Pinnacle, BetPlay/Kambi and the
# original nba-surebets project. Keys are already normalised at import time.
TEAM_ALIASES: dict[str, str] = {
    "atl hawks": "atlanta hawks",
    "atlanta hawks": "atlanta hawks",
    "bkn nets": "brooklyn nets",
    "brooklyn nets": "brooklyn nets",
    "bos celtics": "boston celtics",
    "boston celtics": "boston celtics",
    "cha hornets": "charlotte hornets",
    "charlotte hornets": "charlotte hornets",
    "chi bulls": "chicago bulls",
    "chicago bulls": "chicago bulls",
    "cle cavaliers": "cleveland cavaliers",
    "cleveland cavaliers": "cleveland cavaliers",
    "dal mavericks": "dallas mavericks",
    "dallas mavericks": "dallas mavericks",
    "den nuggets": "denver nuggets",
    "denver nuggets": "denver nuggets",
    "det pistons": "detroit pistons",
    "detroit pistons": "detroit pistons",
    "gsw warriors": "golden state warriors",
    "gs warriors": "golden state warriors",
    "golden state warriors": "golden state warriors",
    "hou rockets": "houston rockets",
    "houston rockets": "houston rockets",
    "ind pacers": "indiana pacers",
    "indiana pacers": "indiana pacers",
    "lac clippers": "los angeles clippers",
    "la clippers": "los angeles clippers",
    "los angeles clippers": "los angeles clippers",
    "lal lakers": "los angeles lakers",
    "la lakers": "los angeles lakers",
    "los angeles lakers": "los angeles lakers",
    "mem grizzlies": "memphis grizzlies",
    "memphis grizzlies": "memphis grizzlies",
    "mia heat": "miami heat",
    "miami heat": "miami heat",
    "mil bucks": "milwaukee bucks",
    "milwaukee bucks": "milwaukee bucks",
    "min timberwolves": "minnesota timberwolves",
    "minnesota timberwolves": "minnesota timberwolves",
    "nop pelicans": "new orleans pelicans",
    "no pelicans": "new orleans pelicans",
    "new orleans pelicans": "new orleans pelicans",
    "nyk knicks": "new york knicks",
    "ny knicks": "new york knicks",
    "new york knicks": "new york knicks",
    "okc thunder": "oklahoma city thunder",
    "oklahoma city thunder": "oklahoma city thunder",
    "orl magic": "orlando magic",
    "orlando magic": "orlando magic",
    "phi 76ers": "philadelphia 76ers",
    "philadelphia 76ers": "philadelphia 76ers",
    "phx suns": "phoenix suns",
    "phoenix suns": "phoenix suns",
    "por trail blazers": "portland trail blazers",
    "portland trail blazers": "portland trail blazers",
    "sac kings": "sacramento kings",
    "sacramento kings": "sacramento kings",
    "sas spurs": "san antonio spurs",
    "sa spurs": "san antonio spurs",
    "san antonio spurs": "san antonio spurs",
    "tor raptors": "toronto raptors",
    "toronto raptors": "toronto raptors",
    "uta jazz": "utah jazz",
    "utah jazz": "utah jazz",
    "was wizards": "washington wizards",
    "washington wizards": "washington wizards",
}

# English and Spanish labels used by Pinnacle and Kambi.
MARKET_ALIASES: dict[str, str] = {
    "moneyline": "moneyline",
    "money line": "moneyline",
    "match winner": "moneyline",
    "winner": "moneyline",
    "linea de dinero": "moneyline",
    "ganador": "moneyline",
    "ganador - prorroga incluida": "moneyline",
    "point spread": "handicap",
    "spread": "handicap",
    "handicap": "handicap",
    "handicap - partido": "handicap",
    "total points": "total",
    "total": "total",
    "over/under": "total",
    "total - partido": "total",
    "total partido": "total",
}

# Kambi shortEnglishLabel values for player props.
PLAYER_MARKETS: dict[str, str] = {
    "player points": "player_points",
    "player rebounds": "player_rebounds",
    "player assists": "player_assists",
    "player threes": "player_threes",
    "player steals": "player_steals",
    "player blocks": "player_blocks",
    "player turnovers": "player_turnovers",
    "player points and rebounds": "player_points_rebounds",
    "player points and assists": "player_points_assists",
    "player rebounds and assists": "player_rebounds_assists",
    "player points assists and rebounds": "player_points_assists_rebounds",
    "player double double": "player_double_double",
    "player triple double": "player_triple_double",
}

MARKETS_WITH_RULES_WARNING = frozenset(
    {
        "handicap",
        "total",
        "team_total",
        *PLAYER_MARKETS.values(),
    }
)


def strip_accents(value: str) -> str:
    decomposed = unicodedata.normalize("NFKD", value)
    return "".join(char for char in decomposed if not unicodedata.combining(char))


def normalize_name(value: str) -> str:
    """Lowercase, remove accents and collapse non-alphanumeric runs."""
    text = strip_accents(value).casefold()
    text = text.replace("&", " and ")
    text = re.sub(r"[^a-z0-9]+", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def canonical_team(value: str) -> str:
    """Return the canonical full team name, or raise ``ValueError``."""
    key = normalize_name(value)
    if key in TEAM_ALIASES:
        return TEAM_ALIASES[key]
    raise ValueError(f"unknown NBA team: {value!r}")


def canonical_market(label: str, short_label: str | None = None) -> str | None:
    """Map a bookmaker market label to a canonical market name."""
    if short_label:
        short_key = normalize_name(short_label)
        if short_key in PLAYER_MARKETS:
            return PLAYER_MARKETS[short_key]

    key = normalize_name(label)
    if key in MARKET_ALIASES:
        return MARKET_ALIASES[key]
    if "total points by" in key or "total del equipo" in key:
        return "team_total"
    if "by the player" in key or "del jugador" in key or "por el jugador" in key:
        return _player_market_from_label(key)
    if "moneyline" in key or "linea de dinero" in key:
        return "moneyline"
    if "point spread" in key or "handicap" in key:
        return "handicap"
    if "total" in key and "points" in key:
        return "total"
    return None


def _player_market_from_label(key: str) -> str | None:
    if "points and assists and rebounds" in key or "puntos asistencias y rebotes" in key:
        return "player_points_assists_rebounds"
    if "points and rebounds" in key:
        return "player_points_rebounds"
    if "points and assists" in key:
        return "player_points_assists"
    if "rebounds and assists" in key:
        return "player_rebounds_assists"
    if "3 point" in key or "three point" in key or "triples" in key:
        return "player_threes"
    if "assist" in key or "asistencias" in key:
        return "player_assists"
    if "rebound" in key or "rebotes" in key:
        return "player_rebounds"
    if "steal" in key or "robos" in key:
        return "player_steals"
    if "block" in key or "bloqueos" in key:
        return "player_blocks"
    if "turnover" in key or "perdidas" in key:
        return "player_turnovers"
    if "points" in key or "puntos" in key:
        return "player_points"
    return None


def event_signature(home: str, away: str) -> tuple[str, str]:
    """Order-independent pair of canonical teams."""
    return tuple(sorted((canonical_team(home), canonical_team(away))))  # type: ignore[return-value]


def selection_side(label: str, home: str, away: str) -> str | None:
    """Map an outcome label to ``home``/``away``/``over``/``under``."""
    key = normalize_name(label)
    if key in ("over", "mas de", "more than", "mas"):
        return "over"
    if key in ("under", "menos de", "less than", "menos"):
        return "under"
    try:
        team = canonical_team(label)
    except ValueError:
        return None
    if team == canonical_team(home):
        return "home"
    if team == canonical_team(away):
        return "away"
    return None


def validate_market_compatibility(market_a: Dict[str, Any], market_b: Dict[str, Any]) -> bool:
    """
    Valida de forma estricta si dos mercados son compatibles para su comparación en surebets:
    - Moneyline solo se compara con Moneyline.
    - Hándicap solo se compara con Hándicap si el valor absoluto de la línea coincide exactamente.
    """
    type_a = canonical_market(market_a.get("market_type", ""))
    type_b = canonical_market(market_b.get("market_type", ""))

    if not type_a or type_a != type_b:
        return False

    if type_a == "moneyline":
        return True

    if type_a == "handicap":
        line_a = market_a.get("line")
        line_b = market_b.get("line")

        if line_a is None or line_b is None:
            return False

        try:
            return abs(float(line_a)) == abs(float(line_b))
        except (ValueError, TypeError):
            return False

    return False

