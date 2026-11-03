"""Tests for capture privacy helpers."""

from recon.sanitize import is_live_url, redact_url, safe_headers, slugify


def test_redacts_token_like_query_values() -> None:
    url = "https://www.betano.co/danae-webapi/api/event?eventId=94443256&token=abc123&league=441g"
    redacted = redact_url(url)
    assert "token=REDACTED" in redacted
    assert "eventId=94443256" in redacted
    assert "league=441g" in redacted


def test_redacts_opaque_query_values() -> None:
    url = "https://example.test/api?x=AbCdEfGhIjKlMnOpQrStUvWxYz012345"
    assert "REDACTED" in redact_url(url)


def test_keeps_safe_headers_only() -> None:
    headers = {
        "Content-Type": "application/json",
        "Set-Cookie": "session=secret",
        "Authorization": "Bearer secret",
        "Date": "Mon, 02 Nov 2026 00:00:00 GMT",
    }
    assert safe_headers(headers) == {
        "content-type": "application/json",
        "date": "Mon, 02 Nov 2026 00:00:00 GMT",
    }


def test_live_url_detection_is_segment_based() -> None:
    assert is_live_url("https://www.betano.co/danae-webapi/api/live/overview/latest")
    assert not is_live_url("https://www.betano.co/sport/baloncesto/ee-uu/nba/441g/")
    assert not is_live_url("https://www.betano.co/livecasino/")


def test_slugify() -> None:
    assert slugify("Cleveland Cavaliers - Oklahoma City Thunder") == (
        "cleveland-cavaliers-oklahoma-city-thunder"
    )
