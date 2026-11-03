"""Tests for capture blocking rules."""

from recon.capture import BLOCK_TEXT_RE


def test_detects_betano_compliance_page() -> None:
    text = "Access to this page is restricted due to security and compliance measures."
    assert BLOCK_TEXT_RE.search(text)


def test_does_not_flag_normal_betting_text() -> None:
    text = "Apuestas de NBA - Cleveland Cavaliers vs Oklahoma City Thunder"
    assert not BLOCK_TEXT_RE.search(text)
