"""Piwi247 provider.

The odds parser is NOT implemented yet: it needs a real sample of the site's
``sports-service/sv/odds/events`` response. Until then ``fetch_odds`` raises instead of
returning made-up prices. Run ``python -m surebets.cli piwi-sample`` to save a raw sample.
"""

from __future__ import annotations

import logging
from datetime import datetime

from surebets.errors import ProviderUnavailableError
from surebets.models import OddsQuote
from surebets.providers.base import OddsProvider

log = logging.getLogger(__name__)
SPORTS_URL = "https://www.piwi247.com/?tab=sports"
ODDS_PATH = "sports-service/sv/odds/events"


class PiwiProvider(OddsProvider):
    bookmaker = "Piwi247"

    def __init__(self, max_events: int = 30, headless: bool = False) -> None:
        self.max_events = max_events
        self.headless = headless

    def parse_payload(self, data: dict, now: datetime) -> list[OddsQuote]:
        raise ProviderUnavailableError(
            "Piwi247: odds parser not implemented (no real payload sample yet); "
            "run `python -m surebets.cli piwi-sample`"
        )

    def capture_raw(self, basketball_only: bool = True) -> list[dict]:
        """Open the public sports page once and return the odds JSON bodies it loads."""
        from playwright.sync_api import sync_playwright  # optional dependency

        bodies: list[dict] = []
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=self.headless)
            try:
                context = browser.new_context(viewport={"width": 360, "height": 800})
                page = context.new_page()

                def on_response(response) -> None:
                    if ODDS_PATH in response.url and (not basketball_only or "sp=4" in response.url):
                        try:
                            bodies.append(response.json())
                        except Exception:  # noqa: BLE001 - non-JSON bodies are ignored
                            log.debug("non-JSON response ignored")

                page.on("response", on_response)
                page.goto(SPORTS_URL, timeout=60000)
                page.wait_for_timeout(8000)
            finally:
                browser.close()
        return bodies

    def fetch_odds(self) -> list[OddsQuote]:
        bodies = self.capture_raw()
        if not bodies:
            raise ProviderUnavailableError("Piwi247: no odds response captured")
        now = datetime.now().astimezone()
        quotes: list[OddsQuote] = []
        for body in bodies:
            quotes.extend(self.parse_payload(body, now))
        return quotes[: self.max_events * 6]
