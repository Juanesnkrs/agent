"""Opportunity log and alert de-duplication (persistence across consecutive scans)."""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path

from surebets.matching import Opportunity


class OpportunityStore:
    def __init__(self, data_dir: str | Path = "data") -> None:
        self.dir = Path(data_dir)
        self.dir.mkdir(parents=True, exist_ok=True)
        self.state_path = self.dir / "alert_state.json"
        self.log_path = self.dir / "opportunities.jsonl"

    def _load(self) -> dict:
        try:
            return json.loads(self.state_path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return {}

    def update(
        self,
        found: list[tuple[Opportunity, float]],
        now: datetime,
        persistence_n: int = 2,
        min_improvement: float = 0.005,
    ) -> list[Opportunity]:
        """Log all ``(opportunity, net_roi)`` pairs; return those that should alert now.

        An opportunity alerts once it was seen in ``persistence_n`` consecutive scans, and
        again only if its net margin improved by ``min_improvement``. Keys that vanish are dropped.
        """
        old, new, to_alert = self._load(), {}, []
        with self.log_path.open("a", encoding="utf-8") as log:
            for opp, net in found:
                entry = old.get(opp.key, {"count": 0, "alerted_roi": None})
                entry["count"] += 1
                alerted = entry["alerted_roi"]
                if entry["count"] >= persistence_n and (alerted is None or net - alerted >= min_improvement):
                    to_alert.append(opp)
                    entry["alerted_roi"] = net
                new[opp.key] = entry
                log.write(json.dumps({
                    "at": now.isoformat(), "key": opp.key, "market": opp.market, "line": opp.line,
                    "legs": [[leg.book, leg.selection, leg.odds] for leg in opp.legs],
                    "gross_roi": opp.roi, "net_roi": net, "count": entry["count"],
                }) + "\n")
        self.state_path.write_text(json.dumps(new), encoding="utf-8")
        return to_alert
