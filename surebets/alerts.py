"""Alert text and Telegram delivery. Never places bets."""

from __future__ import annotations

from datetime import datetime

import httpx

from surebets import arbitrage
from surebets.matching import Opportunity
from surebets.normalize import MARKETS_WITH_RULES_WARNING

_TITLES = {"moneyline": "Ganador", "handicap": "Hándicap", "total": "Total", "team_total": "Total equipo"}
WARNING = "Verifica cuotas, moneda y reglas de ambas casas antes de apostar."
RULES = "Revisa reglas: jugador que no juega, tiempo extra y apuestas anuladas."


def format_alert(
    opp: Opportunity,
    now: datetime,
    commissions: dict[str, float] | None = None,
    max_stake: float = 100.0,
    increment: float = 1.0,
) -> str:
    odds = [leg.odds for leg in opp.legs]
    stakes, worst_profit = arbitrage.capped_stakes(odds, max_stake, increment)
    mins = max(int((opp.start_time - now).total_seconds() // 60), 0)
    age = max(int((now - min(leg.captured_at for leg in opp.legs)).total_seconds() // 60), 0)
    title = _TITLES.get(opp.market, opp.market.replace("_", " "))
    detail = f" {opp.line:g}" if opp.line is not None else ""
    who = f" ({opp.player})" if opp.player else ""
    lines = [
        "Posible surebet (prematch)",
        f"{opp.teams[0].title()} vs {opp.teams[1].title()} - inicia en {mins // 60}h {mins % 60}m",
        f"Mercado: {title}{detail}{who}",
    ]
    lines += [f"- {leg.book}: {leg.selection} @ {leg.odds:g} -> {st:g}" for leg, st in zip(opp.legs, stakes)]
    lines += [
        f"Margen bruto {opp.roi:+.2%} | neto {opp.net_roi(commissions):+.2%}",
        f"Ganancia minima con esos stakes (unidades): {worst_profit:+.2f}",
        f"Datos de hace {age} min.",
        WARNING,
    ]
    if opp.market in MARKETS_WITH_RULES_WARNING:
        lines.append(RULES)
    return "\n".join(lines)


def send_telegram(
    text: str, token: str | None, chat_id: str | None, client: httpx.Client | None = None
) -> bool:
    """Send ``text``; without credentials print it and return False. The token is never logged."""
    if not token or not chat_id:
        print(text, end="\n\n")
        return False
    http = client or httpx.Client(timeout=15.0)
    response = http.post(
        f"https://api.telegram.org/bot{token}/sendMessage", json={"chat_id": chat_id, "text": text}
    )
    return response.status_code == 200
