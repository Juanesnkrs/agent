"""Tests for the verified sites configuration."""

import pytest

from recon.sites import get_site, load_sites

EXPECTED = {"betano", "rushbet", "betsson", "wplay", "bwin", "stake", "codere", "betplay"}


def test_all_eight_sites_are_listed() -> None:
    assert set(load_sites()) == EXPECTED


@pytest.mark.parametrize("name", sorted(EXPECTED))
def test_each_site_is_coljuegos_licensed(name: str) -> None:
    site = get_site(name)
    assert site.country == "CO"
    assert site.license["regulator"] == "Coljuegos"
    assert site.license["evidence_url"].startswith("https://")
    assert site.base_url.startswith("https://")


def test_betano_is_blocked_and_provider_is_unknown() -> None:
    site = get_site("betano")
    assert site.capture is not None
    assert "automatizaci" in site.capture["status"]
    assert site.provider is not None
    assert site.provider["confidence"] == "unknown"
    assert "sin evidencia" in site.provider["name"]


def test_betplay_is_licensed_and_cites_kambi_public_source() -> None:
    site = get_site("betplay")
    assert site.license["legal_entity"] == "Corredor Empresarial S.A."
    assert site.base_url == "https://betplay.com.co/"
    assert site.provider is not None
    assert site.provider["name"] == "Kambi"
    assert site.provider["confidence"] == "public-source"
    assert "kambi.com" in site.provider["evidence_url"]


def test_rushbet_navigation_targets_the_kambi_nba_route() -> None:
    site = get_site("rushbet")
    assert site.navigation is not None
    assert site.navigation["nba_url"].endswith("#filter/basketball/nba")
    assert site.provider is not None
    assert site.provider["confidence"] == "network-observed"
    assert site.capture is not None
    assert "sin bloqueo" in site.capture["status"]
