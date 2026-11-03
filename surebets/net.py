"""Polite HTTP access for public odds endpoints.

Only public, unauthenticated GET requests are allowed. The fetcher enforces a
conservative pace, a hard timeout and at most two retries with growing backoff.
A 403/429, a captcha or a compliance page marks the bookmaker as blocked and is
never retried.
"""

from __future__ import annotations

import random
import time
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from typing import Any

import httpx

from surebets.errors import ProviderBlockedError, ProviderUnavailableError

USER_AGENT = "surebets/0.1 (prematch NBA odds reader)"
BLOCK_MARKERS = (
    "captcha",
    "cf-challenge",
    "just a moment",
    "access denied",
    "forbidden",
    "unusual traffic",
    "are you a robot",
)


@dataclass(frozen=True)
class FetchPolicy:
    """Conservative defaults for prematch scraping."""

    min_interval_seconds: float = 300.0
    min_request_interval_seconds: float = 1.5
    timeout_seconds: float = 30.0
    max_retries: int = 2
    base_backoff_seconds: float = 2.0
    jitter_seconds: float = 1.0


class PoliteFetcher:
    """HTTP GET with per-book throttling and bounded retries."""

    def __init__(
        self,
        policy: FetchPolicy | None = None,
        *,
        client: httpx.Client | None = None,
        clock: Callable[[], float] = time.monotonic,
        sleep: Callable[[float], None] = time.sleep,
        jitter: Callable[[float, float], float] = random.uniform,
    ) -> None:
        self.policy = policy or FetchPolicy()
        self._client = client or httpx.Client(
            timeout=self.policy.timeout_seconds,
            follow_redirects=True,
        )
        self._clock = clock
        self._sleep = sleep
        self._jitter = jitter
        self._last_request: dict[str, float] = {}
        self._last_pass: dict[str, float] = {}

    def get_json(
        self,
        book: str,
        url: str,
        params: Mapping[str, Any] | None = None,
        *,
        pass_start: bool = False,
    ) -> Any:
        """Fetch JSON for ``book``.

        ``pass_start=True`` marks the first request of a new scan and enforces
        the five-minute gap between passes. The remaining requests of the same
        pass only respect a short inter-request delay.
        """
        if pass_start:
            self._start_pass(book)
        else:
            self._throttle_request(book)
        attempts = 0
        while True:
            try:
                response = self._client.get(
                    url,
                    params=params,
                    headers={"User-Agent": USER_AGENT, "Accept": "application/json"},
                )
            except httpx.TimeoutException as exc:
                if attempts >= self.policy.max_retries:
                    raise ProviderUnavailableError(f"{book}: timed out after retries") from exc
                self._backoff(attempts)
                attempts += 1
                continue
            except httpx.HTTPError as exc:
                if attempts >= self.policy.max_retries:
                    raise ProviderUnavailableError(f"{book}: request failed: {exc}") from exc
                self._backoff(attempts)
                attempts += 1
                continue

            status = response.status_code
            if status in (403, 429):
                raise ProviderBlockedError(f"{book}: HTTP {status}")
            if status >= 500:
                if attempts >= self.policy.max_retries:
                    raise ProviderUnavailableError(f"{book}: HTTP {status} after retries")
                self._backoff(attempts)
                attempts += 1
                continue
            if status >= 400:
                raise ProviderUnavailableError(f"{book}: HTTP {status}")

            content_type = response.headers.get("content-type", "")
            if "json" not in content_type.lower() and self._looks_blocked(response.text):
                raise ProviderBlockedError(f"{book}: challenge or captcha page")
            try:
                return response.json()
            except ValueError as exc:
                if self._looks_blocked(response.text):
                    raise ProviderBlockedError(f"{book}: challenge or captcha page") from exc
                raise ProviderUnavailableError(f"{book}: response is not JSON") from exc

    def _start_pass(self, book: str) -> None:
        last = self._last_pass.get(book)
        now = self._clock()
        if last is not None:
            wait = last + self.policy.min_interval_seconds - now
            if wait > 0:
                self._sleep(wait + self._jitter(0.0, self.policy.jitter_seconds))
                now = self._clock()
        self._last_pass[book] = now
        self._last_request[book] = now

    def _throttle_request(self, book: str) -> None:
        last = self._last_request.get(book)
        now = self._clock()
        if last is not None:
            wait = last + self.policy.min_request_interval_seconds - now
            if wait > 0:
                self._sleep(wait + self._jitter(0.0, self.policy.jitter_seconds))
                now = self._clock()
        self._last_request[book] = now

    def _backoff(self, attempt: int) -> None:
        self._sleep(self.policy.base_backoff_seconds * (2**attempt))

    @staticmethod
    def _looks_blocked(text: str) -> bool:
        lowered = text[:4000].lower()
        return any(marker in lowered for marker in BLOCK_MARKERS)

