"""Tests for the hard timeout that protects a capture session."""

import threading

from recon.capture import SESSION_TIMEOUT_SECONDS, HardTimeout


def test_default_session_timeout_is_four_minutes() -> None:
    assert SESSION_TIMEOUT_SECONDS == 240


def test_hard_timeout_calls_exit_when_deadline_expires() -> None:
    called = threading.Event()
    codes: list[int] = []

    def fake_exit(code: int) -> None:
        codes.append(code)
        called.set()

    with HardTimeout(0.05, exit_fn=fake_exit):
        assert called.wait(1.0)

    assert codes == [124]


def test_hard_timeout_is_cancelled_on_normal_exit() -> None:
    called = threading.Event()

    with HardTimeout(0.2, exit_fn=lambda _code: called.set()):
        pass

    assert not called.wait(0.3)
