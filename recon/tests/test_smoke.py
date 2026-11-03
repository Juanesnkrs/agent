"""Smoke tests for the local recon environment."""

from playwright.sync_api import sync_playwright


def test_chromium_launches() -> None:
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page()
        page.set_content("<title>ok</title>")
        assert page.title() == "ok"
        browser.close()
