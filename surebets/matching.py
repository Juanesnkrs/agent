"""Find arbitrages between two books, working directly on ``OddsQuote`` objects.

Quotes are already canonical (see ``normalize``). Home/away orientation is ignored:
sides are expressed with canonical team names, so a book that lists the away team
first still matches. Compared market pairs:

- moneyline: team X on one book against team Y on the other
- handicap: team X at line L against team Y at -L
- total / team_total / player_*: over at line L against under at the same line L

Events match by team pair and a start time within 10 minutes. Two quotes of the
same bookmaker are never paired.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime, timedelta
from itertools import product

from surebets import arbitrage
from surebets.models import OddsQuote
from surebets.normalize import canonical_team, event_signature, normalize_name

log = logging.getLogger(__name__)
START_TOLERANCE = timedelta(minutes=10)


@dataclass(frozen=True)
class Leg:
    book: str
    selection: str
    odds: float
    captured_at: datetime


@dataclass(frozen=True)
class Opportunity:
    teams: tuple[str, str]
    start_time: datetime
    market: str
    line: float | None
    player: str | None
    legs: tuple[Leg, Leg]

    @property
    def roi(self) -> float:
        return arbitrage.guaranteed_return([leg.odds for leg in self.legs])

    def net_roi(self, commissions: dict[str, float] | None = None) -> float:
        """Guaranteed return after per-book commission on winnings (keys lowercase)."""
        rates = commissions or {}
        net = [1 + (leg.odds - 1) * (1 - rates.get(leg.book.lower(), 0.0)) for leg in self.legs]
        return arbitrage.guaranteed_return(net) if all(o > 1.0 for o in net) else -1.0

    @property
    def key(self) -> str:
        legs = "|".join(f"{leg.book}:{leg.selection}" for leg in sorted(self.legs, key=str))
        return f"{self.teams}|{self.start_time:%Y%m%d%H%M}|{self.market}|{self.line}|{self.player}|{legs}"


def _team(q: OddsQuote) -> str:
    if q.selection == "home":
        return canonical_team(q.home)
    if q.selection == "away":
        return canonical_team(q.away)
    raise ValueError(f"not a team selection: {q.selection!r}")


def _classify(q: OddsQuote) -> tuple[tuple, object] | None:
    """Return (group key, side) for a quote, or None when it cannot be compared."""
    m = q.market
    if m == "moneyline":
        return ("moneyline",), _team(q)
    if m == "handicap":
        return (("handicap", abs(q.line)), (_team(q), q.line)) if q.line is not None else None
    if q.line is None:
        return None
    if m == "total" and q.selection in ("over", "under"):
        return ("total", q.line), q.selection
    if m == "team_total":
        who, _, side = q.selection.partition("_")
        if who in ("home", "away") and side in ("over", "under"):
            team = canonical_team(q.home if who == "home" else q.away)
            return ("team_total", team, q.line), side
    if m.startswith("player_") and q.player and q.selection in ("over", "under"):
        return (m, normalize_name(q.player), q.line), q.selection
    return None


def _opposite(kind: str, a: object, b: object) -> bool:
    if kind == "handicap":
        return a[0] != b[0] and a[1] == -b[1]  # type: ignore[index]
    return a != b


def _label(kind: str, side: object, group: tuple) -> str:
    if kind == "handicap":
        return f"{side[0]} {side[1]:+g}"  # type: ignore[index]
    if kind == "moneyline":
        return str(side)
    return f"{side} {group[-1]:g}"


def _events(quotes: list[OddsQuote]) -> dict[tuple, list[OddsQuote]]:
    out: dict[tuple, list[OddsQuote]] = {}
    for q in quotes:
        try:
            sig = event_signature(q.home, q.away)
        except ValueError:
            log.warning("unknown team, skipping event %s vs %s", q.home, q.away)
            continue
        out.setdefault((sig, q.event_id), []).append(q)
    return out


def _best_sides(quotes: list[OddsQuote]) -> dict[tuple, dict[object, OddsQuote]]:
    groups: dict[tuple, dict[object, OddsQuote]] = {}
    for q in quotes:
        try:
            classified = _classify(q)
        except ValueError:
            continue
        if classified is None:
            continue
        group, side = classified
        best = groups.setdefault(group, {})
        if side not in best or q.decimal_odds > best[side].decimal_odds:
            best[side] = q
    return groups


def find_opportunities(
    quotes_a: list[OddsQuote], quotes_b: list[OddsQuote], min_roi: float = 0.0
) -> list[Opportunity]:
    """All cross-book arbitrages with gross ROI above ``min_roi``, best first."""
    found: list[Opportunity] = []
    events_b = _events(quotes_b)
    for (sig, _), qa in _events(quotes_a).items():
        for (sig_b, _), qb in events_b.items():
            if sig_b != sig or abs(qa[0].start_time - qb[0].start_time) > START_TOLERANCE:
                continue
            sides_a, sides_b = _best_sides(qa), _best_sides(qb)
            for group in sides_a.keys() & sides_b.keys():
                for (sa, ra), (sb, rb) in product(sides_a[group].items(), sides_b[group].items()):
                    if ra.bookmaker.lower() == rb.bookmaker.lower():
                        continue
                    if not _opposite(group[0], sa, sb):
                        continue
                    legs = tuple(
                        Leg(r.bookmaker, _label(group[0], s, group), r.decimal_odds, r.captured_at)
                        for s, r in ((sa, ra), (sb, rb))
                    )
                    opp = Opportunity(sig, qa[0].start_time, ra.market, ra.line, ra.player, legs)
                    if opp.roi > min_roi:
                        found.append(opp)
    return sorted(found, key=lambda o: o.roi, reverse=True)
