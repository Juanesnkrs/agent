"""Tests for polite HTTP access."""

from __future__ import annotations

from dataclasses import dataclass

import httpx
import pytest

from surebets.errors import ProviderBlockedError, ProviderUnavailableError
from surebets.net import FetchPolicy, PoliteFetcher


@dataclass
class FakeResponse:
    status_code: int
    payload: object | None = None
    text: str = ""
    headers: dict[str, str] | None = None

    def __post_init__(self) -> None:
        if self.headers is None:
            self.headers = {}

    def json(self) -> object:
        if self.payload is None:
            raise ValueError("not json")
        return self.payload


class FakeClient:
    def __init__(self, responses: list[FakeResponse]) -> None:
        self.responses = list(responses)
        self.calls = 0

    def get(self, *args: object, **kwargs: object) -> FakeResponse:
        self.calls += 1
        return self.responses.pop(0)


class FakeClock:
    def __init__(self) -> None:
        self.now = 0.0
        self.sleeps: list[float] = []

    def __call__(self) -> float:
        return self.now

    def sleep(self, seconds: float) -> None:
        self.sleeps.append(seconds)
        self.now += seconds


def make_fetcher(client: FakeClient, clock: FakeClock, **policy: float) -> PoliteFetcher:
    return PoliteFetcher(
        FetchPolicy(
            min_interval_seconds=300.0,
            min_request_interval_seconds=0.0,
            jitter_seconds=0.0,
            **policy,  # type: ignore[arg-type]
        ),
        client=client,  # type: ignore[arg-type]
        clock=clock,
        sleep=clock.sleep,
        jitter=lambda a, b: 0.0,
    )


def test_returns_json_and_throttles_each_pass() -> None:
    clock = FakeClock()
    client = FakeClient(
        [
            FakeResponse(200, {"ok": 1}, headers={"content-type": "application/json"}),
            FakeResponse(200, {"ok": 2}, headers={"content-type": "application/json"}),
        ]
    )
    fetcher = make_fetcher(client, clock)

    assert fetcher.get_json("betplay", "https://example.test/a", pass_start=True) == {"ok": 1}
    assert fetcher.get_json("betplay", "https://example.test/b", pass_start=True) == {"ok": 2}

    assert clock.sleeps == [pytest.approx(300.0)]


def test_requests_inside_a_pass_use_a_short_delay() -> None:
    clock = FakeClock()
    client = FakeClient(
        [
            FakeResponse(200, {}, headers={"content-type": "application/json"}),
            FakeResponse(200, {}, headers={"content-type": "application/json"}),
        ]
    )
    policy = FetchPolicy(min_interval_seconds=300.0, min_request_interval_seconds=1.5)
    fetcher = PoliteFetcher(
        policy,
        client=client,  # type: ignore[arg-type]
        clock=clock,
        sleep=clock.sleep,
        jitter=lambda a, b: 0.0,
    )

    fetcher.get_json("betplay", "https://example.test/a", pass_start=True)
    fetcher.get_json("betplay", "https://example.test/b")

    assert clock.sleeps == [pytest.approx(1.5)]


def test_books_are_throttled_independently() -> None:
    clock = FakeClock()
    client = FakeClient(
        [
            FakeResponse(200, {}, headers={"content-type": "application/json"}),
            FakeResponse(200, {}, headers={"content-type": "application/json"}),
        ]
    )
    fetcher = make_fetcher(client, clock)

    fetcher.get_json("betplay", "https://example.test/a", pass_start=True)
    fetcher.get_json("pinnacle", "https://example.test/b", pass_start=True)

    assert clock.sleeps == []


def test_retries_server_errors_with_growing_backoff() -> None:
    clock = FakeClock()
    client = FakeClient(
        [
            FakeResponse(503),
            FakeResponse(500),
            FakeResponse(200, {"ok": True}, headers={"content-type": "application/json"}),
        ]
    )
    fetcher = make_fetcher(client, clock)

    assert fetcher.get_json("betplay", "https://example.test/a") == {"ok": True}
    assert clock.sleeps == [pytest.approx(2.0), pytest.approx(4.0)]


def test_gives_up_after_two_retries() -> None:
    clock = FakeClock()
    client = FakeClient([FakeResponse(503), FakeResponse(503), FakeResponse(503)])
    fetcher = make_fetcher(client, clock)

    with pytest.raises(ProviderUnavailableError):
        fetcher.get_json("betplay", "https://example.test/a")
    assert client.calls == 3


@pytest.mark.parametrize("status", [403, 429])
def test_block_is_not_retried(status: int) -> None:
    clock = FakeClock()
    client = FakeClient([FakeResponse(status)])
    fetcher = make_fetcher(client, clock)

    with pytest.raises(ProviderBlockedError):
        fetcher.get_json("betplay", "https://example.test/a")
    assert client.calls == 1


def test_captcha_page_is_treated_as_block() -> None:
    clock = FakeClock()
    client = FakeClient([FakeResponse(200, text="<html>Please solve the CAPTCHA</html>")])
    fetcher = make_fetcher(client, clock)

    with pytest.raises(ProviderBlockedError):
        fetcher.get_json("betplay", "https://example.test/a")


def test_timeout_retries_then_raises() -> None:
    clock = FakeClock()

    class TimeoutClient:
        calls = 0

        def get(self, *args: object, **kwargs: object) -> FakeResponse:
            self.calls += 1
            raise httpx.ReadTimeout("slow")

    client = TimeoutClient()
    fetcher = PoliteFetcher(
        FetchPolicy(min_interval_seconds=0.0, max_retries=2, jitter_seconds=0.0),
        client=client,  # type: ignore[arg-type]
        clock=clock,
        sleep=clock.sleep,
        jitter=lambda a, b: 0.0,
    )

    with pytest.raises(ProviderUnavailableError):
        fetcher.get_json("betplay", "https://example.test/a")
    assert client.calls == 3
