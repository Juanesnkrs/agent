"""Arbitrage math for decimal odds.

A set of mutually exclusive, exhaustive outcomes (over/under, team A/team B)
priced at decimal odds o_1..o_n is an arbitrage when the implied
probabilities sum to less than one:

    S = sum(1 / o_i) < 1

Staking each outcome in proportion to its implied probability,
stake_i = B * (1 / o_i) / S, pays the same B / S whichever outcome wins,
so the guaranteed return on the bankroll B is 1 / S - 1.
"""

import math
from collections.abc import Sequence


def _check(odds: Sequence[float]) -> None:
    if len(odds) < 2:
        raise ValueError("an arbitrage needs at least two outcomes")
    for o in odds:
        if not (o > 1.0 and math.isfinite(o)):
            raise ValueError(f"decimal odds must be finite and > 1, got {o}")


def implied_probability(odds: float) -> float:
    """Probability the bookmaker's price implies, including its margin."""
    return 1.0 / odds


def book_sum(odds: Sequence[float]) -> float:
    """Sum of implied probabilities; below 1 means an arbitrage exists."""
    _check(odds)
    return sum(1.0 / o for o in odds)


def is_arbitrage(odds: Sequence[float]) -> bool:
    return book_sum(odds) < 1.0


def guaranteed_return(odds: Sequence[float]) -> float:
    """Return on total stake locked in by optimal staking (negative if no arb).

    For two outcomes this equals o1 * o2 / (o1 + o2) - 1.
    """
    return 1.0 / book_sum(odds) - 1.0


def optimal_stakes(odds: Sequence[float], bankroll: float) -> list[float]:
    """Split `bankroll` so every outcome pays the same amount."""
    s = book_sum(odds)
    return [bankroll * (1.0 / o) / s for o in odds]


def capped_stakes(
    odds: Sequence[float], max_stake: float, increment: float = 1.0
) -> tuple[list[float], float]:
    """Stakes that keep every leg at or below `max_stake`, rounded down to
    the bookmaker's `increment`.

    Sportsbooks limit or close accounts that repeatedly bet the maximum,
    so in practice each leg is kept modest. Returns the stakes and the
    worst-case profit after rounding (rounding can eat a thin edge).
    """
    s = book_sum(odds)
    weights = [(1.0 / o) / s for o in odds]
    bankroll = max_stake / max(weights)
    stakes = [math.floor(bankroll * w / increment) * increment for w in weights]
    total = sum(stakes)
    worst_payout = min(st * o for st, o in zip(stakes, odds))
    return stakes, worst_payout - total

