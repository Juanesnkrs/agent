"""Command line: ``scan``, ``watch`` and ``piwi-sample``. Detection and alerts only."""

from __future__ import annotations

import argparse
import json
import os
import time
from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from datetime import datetime
from itertools import combinations
from pathlib import Path

from surebets.alerts import format_alert, send_telegram
from surebets.errors import ProviderBlockedError, ProviderError
from surebets.filters import prematch_filter
from surebets.matching import find_opportunities
from surebets.providers.base import OddsProvider
from surebets.store import OpportunityStore

MIN_INTERVAL_SECONDS = 300


@dataclass
class Config:
    prematch_min_minutes: float = 30
    max_odds_age_minutes: float = 10
    min_net_margin: float = 0.01
    persistence_n: int = 2
    max_stake: float = 100.0
    commissions: dict[str, float] = field(default_factory=dict)

    @classmethod
    def from_env(cls, env: Mapping[str, str] = os.environ) -> Config:
        g = env.get
        return cls(
            float(g("PREMATCH_MIN_MINUTES", 30)), float(g("MAX_ODDS_AGE_MINUTES", 10)),
            float(g("MIN_NET_MARGIN", 0.01)), int(g("PERSISTENCE_N", 2)), float(g("MAX_STAKE", 100)),
            {k[11:].lower(): float(v) for k, v in env.items() if k.startswith("COMMISSION_")},
        )


def scan(
    providers: list[OddsProvider],
    now: datetime,
    cfg: Config,
    store: OpportunityStore,
    notify: Callable[[str], object] = print,
) -> list[str]:
    """One pass: read every provider, compare each pair, alert on new opportunities."""
    lists = []
    for provider in providers:
        try:
            quotes = provider.fetch_odds()
        except ProviderBlockedError as exc:
            print(f"[bloqueada] {exc}")
            continue
        except ProviderError as exc:
            print(f"[error] {exc}")
            continue
        kept, stats = prematch_filter(quotes, now, cfg.prematch_min_minutes, cfg.max_odds_age_minutes)
        print(f"{type(provider).__name__}: {len(kept)} cuotas utiles, descartadas {stats}")
        if kept:
            lists.append(kept)
    if len(lists) < 2:
        print("Datos insuficientes: se necesitan cuotas de al menos dos casas.")
        return []
    found = []
    for a, b in combinations(lists, 2):
        for opp in find_opportunities(a, b):
            net = opp.net_roi(cfg.commissions)
            if net >= cfg.min_net_margin:
                found.append((opp, net))
    alerts = []
    for opp in store.update(found, now, cfg.persistence_n):
        text = format_alert(opp, now, cfg.commissions, cfg.max_stake)
        notify(text)
        alerts.append(text)
    print(f"Oportunidades netas >= {cfg.min_net_margin:.1%}: {len(found)} | alertas: {len(alerts)}")
    return alerts


def _default_providers() -> list[OddsProvider]:
    from surebets.providers.betplay import BetPlayProvider
    from surebets.providers.piwi import PiwiProvider

    return [BetPlayProvider(), PiwiProvider()]


def _notifier(env: Mapping[str, str]) -> Callable[[str], object]:
    return lambda text: send_telegram(text, env.get("TELEGRAM_BOT_TOKEN"), env.get("TELEGRAM_CHAT_ID"))


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="surebets")
    sub = parser.add_subparsers(dest="cmd", required=True)
    sub.add_parser("scan")
    watch = sub.add_parser("watch")
    watch.add_argument("--interval", type=int, default=MIN_INTERVAL_SECONDS)
    watch.add_argument("--max-iter", type=int, default=12)
    sub.add_parser("piwi-sample")
    args = parser.parse_args(argv)

    if args.cmd == "piwi-sample":
        from surebets.providers.piwi import PiwiProvider

        bodies = PiwiProvider().capture_raw()
        Path("data").mkdir(exist_ok=True)
        Path("data/piwi_sample.json").write_text(json.dumps(bodies, ensure_ascii=False, indent=1), "utf-8")
        print(f"{len(bodies)} respuestas guardadas en data/piwi_sample.json")
        return 0

    cfg, store, notify = Config.from_env(), OpportunityStore(), _notifier(os.environ)
    providers = _default_providers()
    rounds = 1 if args.cmd == "scan" else args.max_iter
    for i in range(rounds):
        scan(providers, datetime.now().astimezone(), cfg, store, notify)
        if i < rounds - 1:
            time.sleep(max(args.interval, MIN_INTERVAL_SECONDS))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
