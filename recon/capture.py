"""Single-pass, read-only capture of one sportsbook.

Usage:
    python -m recon.capture --site betano

The browser is headed by default and emulates a 360x800 mobile Chrome.
No login, no stealth, no proxy rotation and no captcha handling are used.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import random
import re
import sys
import threading
import time
from collections.abc import Callable
from datetime import datetime
from pathlib import Path
from urllib.parse import urlsplit

from playwright.sync_api import Error as PWError
from playwright.sync_api import sync_playwright

from recon.sanitize import is_live_url, redact_url, safe_headers, slugify
from recon.sites import ROOT, Site, get_site

VIEWPORT = {"width": 360, "height": 800}
LOCALE = "es-CO"
TIMEZONE = "America/Bogota"
MOBILE_UA = (
    "Mozilla/5.0 (Linux; Android 14; Pixel 8) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/156.0.0.0 Mobile Safari/537.36"
)
MAX_BODY_BYTES = 15 * 1024 * 1024
SESSION_TIMEOUT_SECONDS = 240.0


class HardTimeout:
    """Abort the whole capture process when the session deadline expires.

    Playwright's sync API can block inside a call, so checking a deadline
    between steps is not enough. The timer therefore calls ``os._exit`` by
    default, which stops a hung browser call as well.
    """

    def __init__(
        self,
        seconds: float = SESSION_TIMEOUT_SECONDS,
        exit_fn: Callable[[int], None] = os._exit,
    ) -> None:
        self.seconds = seconds
        self.exit_fn = exit_fn
        self._timer: threading.Timer | None = None

    def __enter__(self) -> "HardTimeout":
        self._timer = threading.Timer(self.seconds, self._fire)
        self._timer.daemon = True
        self._timer.start()
        return self

    def _fire(self) -> None:
        print(f"[timeout] session exceeded {self.seconds:g}s; aborting", flush=True)
        self.exit_fn(124)

    def __exit__(self, exc_type, exc, tb) -> None:
        if self._timer is not None:
            self._timer.cancel()


CONSENT_LABELS = (
    r"permitir todo",
    r"permitir todas",
    r"aceptar todas",
    r"aceptar todo",
    r"aceptar cookies",
    r"^aceptar$",
    r"^acepto$",
    r"rechazar todo",
    r"rechazar todas",
    r"soy mayor",
    r"tengo (m[aá]s de )?18",
    r"mayor de 18",
)
DANGEROUS_RE = re.compile(
    r"apuesta|registr|dep[oó]sito|bonus|promoci[oó]n|retirar|ingresar",
    re.IGNORECASE,
)
LEGAL_LINK_RE = re.compile(
    r"t[eé]rminos|condiciones|legal|privacidad|privacy|ayuda|help|soporte|"
    r"support|juego responsable|responsible|reglamento|eula|\btoc\b|"
    r"contacto|contact",
    re.IGNORECASE,
)
LEGAL_HREF_RE = re.compile(
    r"/(?:terms?|terminos?|legal|privacy|privacidad|help|ayuda|support|soporte|"
    r"responsible|eula|toc|contact)(?:[/?#]|$)",
    re.IGNORECASE,
)
BLOCK_TEXT_RE = re.compile(
    r"captcha|verify you are human|unusual traffic|access denied|"
    r"access to this page is restricted|security and compliance measures|"
    r"no disponible en tu pa[ií]s|not available in your country|"
    r"checking your browser|just a moment|attention required|"
    r"desaf[ií]o de seguridad",
    re.IGNORECASE,
)
BLOCK_URL_RE = re.compile(
    r"captcha|turnstile|access-denied|geo.?block|/verify(?:/|$)",
    re.IGNORECASE,
)

NBA_NICKNAMES = [
    "Hawks", "Celtics", "Nets", "Hornets", "Bulls", "Cavaliers", "Mavericks",
    "Nuggets", "Pistons", "Warriors", "Rockets", "Pacers", "Clippers", "Lakers",
    "Grizzlies", "Heat", "Bucks", "Timberwolves", "Pelicans", "Knicks", "Thunder",
    "Magic", "76ers", "Suns", "Blazers", "Kings", "Spurs", "Raptors", "Jazz",
    "Wizards",
]
MARKET_TERMS = [
    "Ganador", "Hándicap", "Handicap", "Total", "Puntos", "Rebotes",
    "Asistencias", "Moneyline", "Spread", "Over", "Under", "Jugador",
    "Player", "PLNP", "PLTR", "PALA", "H2HT", "OUHO", "OUAO",
]


class BlockedSite(RuntimeError):
    """Raised when an anti-bot or geo-block signal is observed."""


def human_pause(low: float = 3.0, high: float = 8.0) -> None:
    time.sleep(random.uniform(low, high))


def settle(page, milliseconds: int = 2500) -> None:
    try:
        page.wait_for_load_state("domcontentloaded", timeout=45000)
    except PWError:
        pass
    page.wait_for_timeout(milliseconds)


def element_text(element) -> str:
    try:
        text = element.inner_text(timeout=700)
    except PWError:
        text = element.get_attribute("aria-label") or ""
    return re.sub(r"\s+", " ", text or "").strip()


def internal_href(href: str | None) -> bool:
    if not href:
        return False
    return href.startswith("/") or "www.betano.co" in href or href.startswith("https://betano.co")


def is_legal_link(text: str | None, href: str | None = None) -> bool:
    """Reject terms, help, privacy and other legal/support destinations."""
    return bool(
        LEGAL_LINK_RE.search(text or "")
        or (href and LEGAL_HREF_RE.search(href))
    )


def find_clickable(
    page,
    text_pattern: str,
    *,
    exact: bool = False,
    href_pattern: str | None = None,
    max_scan: int = 120,
):
    """Find one visible button, tab or link by text and optional href."""
    regex = re.compile(text_pattern, re.IGNORECASE)
    for selector in ("button", "[role=button]", "[role=tab]", "a"):
        locator = page.locator(selector)
        try:
            count = min(locator.count(), max_scan)
        except PWError:
            continue
        for index in range(count):
            element = locator.nth(index)
            try:
                if not element.is_visible():
                    continue
                text = element_text(element)
                if not text or len(text) > 80:
                    continue
                href = element.get_attribute("href") or ""
                if is_legal_link(text, href):
                    continue
                if href_pattern:
                    if not internal_href(href) or not re.search(href_pattern, href, re.IGNORECASE):
                        continue
                if exact:
                    if text.casefold() != text_pattern.casefold():
                        continue
                elif not regex.search(text):
                    continue
                return element, text
            except PWError:
                continue
    return None, None


def click_element(page, element, recorder: "Recorder", label: str) -> bool:
    try:
        element.scroll_into_view_if_needed(timeout=3000)
        element.click(timeout=6000)
        recorder.action(label, "click")
        settle(page, 2200)
        recorder.flush()
        return True
    except PWError as exc:
        recorder.action(label, "click_failed", str(exc)[:240])
        return False


def handle_consent(page, recorder: "Recorder") -> None:
    """Accept cookie/age banners only when the button is simple and visible."""
    clicked = 0
    for _attempt in range(2):
        element = None
        text = ""
        for pattern in CONSENT_LABELS:
            element, text = find_clickable(page, pattern)
            if element:
                break
        if not element:
            if clicked == 0:
                recorder.action("consent", "not_found")
            break
        if DANGEROUS_RE.search(text):
            recorder.action("consent", "skipped_dangerous_text", text)
            break
        if click_element(page, element, recorder, f"consent:{text}"):
            clicked += 1
            recorder.screenshot(page, f"consent-{clicked}")
            recorder.flush()
            human_pause(1.5, 3.0)
        else:
            break


def dismiss_overlay(page, recorder: "Recorder") -> None:
    """Close a visible marketing/login overlay without touching its form."""
    for selector in (
        'button[aria-label*="cerrar" i]',
        'button[aria-label*="close" i]',
        'button[title*="cerrar" i]',
        'button[title*="close" i]',
        'button:has-text("×")',
        'button:has-text("✕")',
    ):
        locator = page.locator(selector)
        try:
            count = min(locator.count(), 10)
        except PWError:
            continue
        for index in range(count):
            element = locator.nth(index)
            try:
                if not element.is_visible():
                    continue
                recorder.action("overlay:dismiss", "click", selector)
                element.click(timeout=5000)
                settle(page, 1200)
                recorder.flush()
                return
            except PWError:
                continue
    try:
        page.keyboard.press("Escape")
        settle(page, 800)
    except PWError:
        pass


def detect_block(page, recorder: "Recorder") -> dict | None:
    """Return evidence when an anti-bot or geo-block signal is present."""
    try:
        title = page.title()
    except PWError:
        title = ""
    if BLOCK_TEXT_RE.search(title):
        return {"kind": "title", "value": title[:300]}

    try:
        body = page.locator("body").inner_text(timeout=4000)[:10000]
    except PWError:
        body = ""
    if BLOCK_TEXT_RE.search(body) and not re.search(
        r"cuota|apuesta|baloncesto|nba", body, re.IGNORECASE
    ):
        return {"kind": "body", "value": body[:500]}

    if BLOCK_URL_RE.search(page.url):
        return {"kind": "url", "url": redact_url(page.url)}

    for entry in reversed(recorder.responses[-30:]):
        if entry.get("status") in (403, 429) and entry.get("resource_type") in (
            "document",
            "xhr",
            "fetch",
        ):
            return {
                "kind": "http",
                "status": entry["status"],
                "url": entry["url"],
            }
    return None


class Recorder:
    """Collect JSON responses, redacting secrets and hiding live bodies."""

    def __init__(self, site: Site, run_dir: Path):
        self.site = site
        self.run_dir = run_dir
        self.json_dir = run_dir / "json"
        self.shots_dir = run_dir / "screenshots"
        self.json_dir.mkdir(parents=True, exist_ok=True)
        self.shots_dir.mkdir(parents=True, exist_ok=True)

        self.steps: list[dict] = []
        self.responses: list[dict] = []
        self.failures: list[dict] = []
        self.screenshots: list[dict] = []
        self._pending: list[tuple[object, dict]] = []
        self._started: dict[int, float] = {}
        self._attached: set[int] = set()
        self._hashes: dict[str, str] = {}
        self._seq = 0
        self._shot_seq = 0
        self._jsonl = (run_dir / "responses.jsonl").open("a", encoding="utf-8")

    def attach(self, page) -> None:
        if id(page) in self._attached:
            return
        self._attached.add(id(page))
        page.on("request", self._on_request)
        page.on("response", self._on_response)
        page.on("requestfailed", self._on_failed)

    def _on_request(self, request) -> None:
        self._started[id(request)] = time.perf_counter()

    def _on_response(self, response) -> None:
        content_type = (response.headers.get("content-type") or "").lower()
        resource_type = response.request.resource_type
        if "json" not in content_type and resource_type not in ("xhr", "fetch"):
            return
        if (
            "json" not in content_type
            and content_type
            and not content_type.startswith("text/plain")
        ):
            return

        self._seq += 1
        started = self._started.pop(id(response.request), None)
        duration_ms = round((time.perf_counter() - started) * 1000, 1) if started else None
        url = redact_url(response.url)
        live = is_live_url(response.url)
        entry = {
            "seq": self._seq,
            "url": url,
            "method": response.request.method,
            "status": response.status,
            "resource_type": resource_type,
            "content_type": content_type,
            "content_length_header": response.headers.get("content-length"),
            "duration_ms": duration_ms,
            "headers": safe_headers(response.headers),
            "is_live": live,
            "discarded_reason": "live" if live else None,
        }
        self._pending.append((response, entry))
        flag = " LIVE-DISCARDED" if live else ""
        print(f"[json {self._seq:03d}] {response.status} {response.request.method} "
              f"{url}{flag}")

    def _on_failed(self, request) -> None:
        self.failures.append(
            {
                "url": redact_url(request.url),
                "method": request.method,
                "resource_type": request.resource_type,
                "failure": request.failure,
            }
        )

    def flush(self) -> None:
        while self._pending:
            response, entry = self._pending.pop(0)
            self._finalize(response, entry)
            self.responses.append(entry)
            self._jsonl.write(json.dumps(entry, ensure_ascii=False) + "\n")
            self._jsonl.flush()

    def _finalize(self, response, entry: dict) -> None:
        if entry["is_live"]:
            return
        try:
            body = response.body()
        except PWError as exc:
            entry["body_error"] = str(exc)[:240]
            return
        entry["body_bytes"] = len(body)
        if not body or len(body) > MAX_BODY_BYTES:
            entry["body_skipped"] = "empty_or_too_large"
            return
        try:
            parsed = json.loads(body.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError):
            entry["body_skipped"] = "not_json"
            return

        digest = hashlib.sha256(body).hexdigest()
        entry["sha256"] = digest
        entry["json_kind"] = type(parsed).__name__
        if isinstance(parsed, dict):
            entry["top_keys"] = list(parsed)[:25]

        if digest in self._hashes:
            entry["duplicate_of"] = self._hashes[digest]
            return

        path_part = urlsplit(entry["url"]).path.rsplit("/", 1)[-1] or "root"
        filename = f"{entry['seq']:04d}-{slugify(path_part)}-{entry['status']}.json"
        file_path = self.json_dir / filename
        file_path.write_bytes(body)
        self._hashes[digest] = filename
        entry["body_file"] = str(file_path.relative_to(self.run_dir)).replace("\\", "/")
        print(f"          saved {entry['body_file']} ({len(body)} bytes)")

    def action(self, name: str, result: str, detail: str | None = None) -> None:
        step = {
            "at": datetime.now().astimezone().isoformat(timespec="seconds"),
            "action": name,
            "result": result,
        }
        if detail:
            step["detail"] = detail
        self.steps.append(step)
        suffix = f" | {detail}" if detail else ""
        print(f"[step] {name}: {result}{suffix}")

    def screenshot(self, page, name: str) -> Path | None:
        self._shot_seq += 1
        path = self.shots_dir / f"{self._shot_seq:02d}-{slugify(name)}.png"
        try:
            page.screenshot(path=str(path))
        except PWError as exc:
            self.action(f"screenshot:{name}", "failed", str(exc)[:160])
            return None
        relative = str(path.relative_to(self.run_dir)).replace("\\", "/")
        self.screenshots.append({"name": name, "file": relative, "url": page.url})
        self.action(f"screenshot:{name}", "ok", relative)
        return path

    def close(self) -> None:
        self.flush()
        self._jsonl.close()


def go(page, recorder: Recorder, url: str, name: str) -> None:
    recorder.action(f"goto:{name}", "start", redact_url(url))
    page.goto(url, wait_until="domcontentloaded", timeout=60000)
    settle(page, 3500)
    recorder.flush()
    recorder.screenshot(page, name)
    evidence = detect_block(page, recorder)
    if evidence:
        raise BlockedSite(json.dumps(evidence, ensure_ascii=False))


def open_sportsbook(page, recorder: Recorder, site: Site) -> None:
    """Open the sportsbook, preferring a known URL over UI labels."""
    navigation = site.navigation or {}
    url = navigation.get("sportsbook_url")
    if url:
        recorder.action("nav:sportsbook", "direct", redact_url(url))
        go(page, recorder, url, "sportsbook")
        settle(page, 6000)
        recorder.flush()
        return

    label = navigation.get("sportsbook_label")
    if label:
        element, text = find_clickable(page, label)
        if element:
            recorder.action("nav:sportsbook", "link", text)
            click_element(page, element, recorder, "nav:sportsbook")
            settle(page, 5000)
            recorder.flush()
            recorder.screenshot(page, "sportsbook")
            return

    recorder.action("nav:sportsbook", "not_configured")


def navigate_to_basketball(page, recorder: Recorder, site: Site) -> None:
    navigation = site.navigation or {}
    if navigation.get("nba_url"):
        recorder.action("nav:basketball", "skipped_direct_nba")
        return
    href_pattern = None if navigation else r"/sport/baloncesto"
    element, text = find_clickable(
        page, r"baloncesto|basketball", href_pattern=href_pattern
    )
    if element:
        recorder.action("nav:basketball", "link", text)
        click_element(page, element, recorder, "nav:basketball")
    else:
        recorder.action("nav:basketball", "link_not_visible")
        if not navigation:
            go(page, recorder, site.base_url + "sport/baloncesto/", "basketball")
    recorder.screenshot(page, "basketball")


def navigate_to_nba(page, recorder: Recorder, site: Site) -> None:
    navigation = site.navigation or {}
    url = navigation.get("nba_url")
    if url:
        recorder.action("nav:nba", "direct", redact_url(url))
        go(page, recorder, url, "nba")
        recorder.screenshot(page, "nba")
        return

    href_pattern = None if navigation else r"/nba/"
    element, text = find_clickable(
        page, r"^nba$", exact=True, href_pattern=href_pattern
    )
    if not element:
        element, text = find_clickable(
            page, r"\bnba\b", href_pattern=href_pattern
        )
    if element:
        recorder.action("nav:nba", "link", text)
        click_element(page, element, recorder, "nav:nba")
    else:
        recorder.action("nav:nba", "link_not_visible")
        go(
            page,
            recorder,
            site.base_url + "sport/baloncesto/ee-uu/nba/441g/",
            "nba",
        )
    recorder.screenshot(page, "nba")


def choose_prematch(page, recorder: Recorder) -> None:
    for label in (r"pr[oó]ximamente", r"pr[oó]ximos", r"^hoy$"):
        element, text = find_clickable(page, label)
        if element and not re.search(r"en vivo|live", text, re.IGNORECASE):
            recorder.action("filter:prematch", "click", text)
            click_element(page, element, recorder, f"filter:{text}")
            recorder.screenshot(page, "prematch")
            return
    recorder.action("filter:prematch", "not_found")


def open_first_event(page, recorder: Recorder, site: Site) -> str | None:
    navigation = site.navigation or {}
    event_url = navigation.get("event_url")
    if event_url:
        recorder.action("event:open", "direct", redact_url(event_url))
        go(page, recorder, event_url, "event")
        recorder.screenshot(page, "event")
        return page.url

    selectors = (
        'a[href*="/cuotas-de-partido/"]',
        'a[href*="#event/"]',
        'a[href*="/event/"]',
        'a[href*="/e/"]',
        '[data-event-id]',
        '[data-testid*="event"]',
    )
    candidates: list[tuple[bool, object, str, str]] = []
    for selector in selectors:
        locator = page.locator(selector)
        try:
            count = min(locator.count(), 150)
        except PWError:
            continue
        for index in range(count):
            element = locator.nth(index)
            try:
                if not element.is_visible():
                    continue
                href = element.get_attribute("href") or ""
                marker = element.get_attribute("data-event-id") or ""
                text = element_text(element)
                if "winnerspecials" in href or len(text) < 8:
                    continue
                if re.search(r"en vivo|\blive\b", text, re.IGNORECASE):
                    continue
                haystack = f"{text} {href}".casefold()
                priority = "lakers" in haystack and "heat" in haystack
                candidates.append(
                    (priority, element, text, href or f"data-event-id={marker}")
                )
            except PWError:
                continue
        if candidates:
            break

    if not candidates:
        recorder.action("event:open", "not_found")
        return None

    priority = [item for item in candidates if item[0]]
    chosen = (
        priority[0]
        if priority
        else next(
            (item for item in candidates if " - " in item[2]),
            candidates[0],
        )
    )
    _priority, element, text, href = chosen
    recorder.action("event:open", "click", f"{text} | {href}")
    if not click_element(page, element, recorder, "event:open"):
        return None
    recorder.screenshot(page, "event")
    return page.url


def open_players_tab(page, recorder: Recorder) -> None:
    tab_labels = (
        r"^jugadores$",
        r"^jugadores \(",
        r"^player props$",
        r"^props de jugador$",
        r"^apuestas de jugador$",
        r"^todo$",
        r"^todos$",
        r"^todos los mercados$",
        r"^mercados$",
    )
    for label in tab_labels:
        element, text = find_clickable(page, label, exact=True)
        if element:
            recorder.action("tab:players", "click", text)
            click_element(page, element, recorder, f"tab:{text}")
            recorder.screenshot(page, "players-tab")
            break
    else:
        recorder.action("tab:players", "not_found")

    # One pass of scrolling to trigger lazy-loaded player markets.
    try:
        page.mouse.move(VIEWPORT["width"] // 2, VIEWPORT["height"] // 2)
        for _ in range(3):
            page.mouse.wheel(0, 900)
            page.wait_for_timeout(1400)
            recorder.flush()
    except PWError:
        pass
    recorder.screenshot(page, "players-scrolled")

    for label in (
        "Puntos",
        "Rebotes",
        "Asistencias",
        "Triples",
        "Puntos + Rebotes",
        "Puntos + Asistencias",
        "Rebotes + Asistencias",
        "Puntos + Rebotes + Asistencias",
    ):
        element, text = find_clickable(page, rf"^{re.escape(label)}$", exact=True)
        if element:
            recorder.action(f"props:{label}", "click", text)
            click_element(page, element, recorder, f"props:{label}")
            recorder.screenshot(page, f"props-{slugify(label)}")
    recorder.flush()


def odds_count(blob: str) -> int:
    total = 0
    for match in re.finditer(r'"(?:price|odds|cuota)"\s*:\s*([0-9]+(?:\.[0-9]+)?)', blob):
        value = float(match.group(1))
        if 1.01 <= value <= 100:
            total += 1
    return total


def score_capture(run_dir: Path, responses: list[dict]) -> list[dict]:
    """Lightweight ranking so the Phase 2 answer is data-driven."""
    url_by_file = {entry.get("body_file"): entry.get("url") for entry in responses}
    ranked: list[dict] = []
    for file_path in sorted((run_dir / "json").glob("*.json")):
        relative = str(file_path.relative_to(run_dir)).replace("\\", "/")
        try:
            data = json.loads(file_path.read_text(encoding="utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError):
            continue
        blob = json.dumps(data, ensure_ascii=False)
        teams = sorted(
            {nick for nick in NBA_NICKNAMES if re.search(rf"\b{re.escape(nick)}\b", blob, re.I)}
        )
        markets = sorted({term for term in MARKET_TERMS if term.casefold() in blob.casefold()})
        odds = odds_count(blob)
        if len(teams) >= 6:
            kind = "event-list"
        elif len(markets) >= 5 and len(teams) <= 4:
            kind = "event-markets"
        else:
            kind = "other"
        ranked.append(
            {
                "file": relative,
                "url": url_by_file.get(relative),
                "kind": kind,
                "teams": teams,
                "team_count": len(teams),
                "markets": markets,
                "market_count": len(markets),
                "odds_count": odds,
                "score": len(teams) * 12 + len(markets) * 4 + min(odds, 300),
                "bytes": file_path.stat().st_size,
            }
        )
    ranked.sort(key=lambda item: item["score"], reverse=True)
    (run_dir / "candidates.json").write_text(
        json.dumps(ranked, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    return ranked


def write_manifest(
    run_dir: Path,
    site: Site,
    recorder: Recorder,
    started_at: str,
    blocked: bool,
    block_evidence: dict | None,
    error: str | None,
    final_url: str | None,
) -> None:
    manifest = {
        "site": site.name,
        "base_url": site.base_url,
        "run_id": run_dir.name,
        "started_at": started_at,
        "finished_at": datetime.now().astimezone().isoformat(timespec="seconds"),
        "viewport": VIEWPORT,
        "locale": LOCALE,
        "timezone": TIMEZONE,
        "user_agent": MOBILE_UA,
        "final_url": final_url,
        "blocked": blocked,
        "block_evidence": block_evidence,
        "error": error,
        "steps": recorder.steps,
        "screenshots": recorder.screenshots,
        "responses": recorder.responses,
        "failures": recorder.failures,
        "summary": {
            "json_responses": len(recorder.responses),
            "live_discarded": sum(1 for item in recorder.responses if item.get("is_live")),
            "bodies_saved": sum(1 for item in recorder.responses if item.get("body_file")),
            "failed_requests": len(recorder.failures),
        },
    }
    (run_dir / "manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8"
    )


def _run(site: Site, headless: bool) -> int:
    run_id = datetime.now().strftime("%Y%m%d-%H%M%S")
    run_dir = ROOT / "recon" / "raw" / site.name / run_id
    run_dir.mkdir(parents=True, exist_ok=True)
    recorder = Recorder(site, run_dir)
    started_at = datetime.now().astimezone().isoformat(timespec="seconds")
    blocked = False
    block_evidence = None
    error = None
    final_url = None

    print(f"site={site.name} run_dir={run_dir}")
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=headless)
        context = browser.new_context(
            viewport=VIEWPORT,
            screen=VIEWPORT,
            device_scale_factor=1,
            is_mobile=True,
            has_touch=True,
            locale=LOCALE,
            timezone_id=TIMEZONE,
            user_agent=MOBILE_UA,
        )
        page = context.new_page()
        context.on("page", recorder.attach)
        recorder.attach(page)

        try:
            go(page, recorder, site.base_url, "home")
            handle_consent(page, recorder)
            dismiss_overlay(page, recorder)
            human_pause()
            recorder.screenshot(page, "home-ready")

            open_sportsbook(page, recorder, site)
            handle_consent(page, recorder)
            dismiss_overlay(page, recorder)
            human_pause()

            navigate_to_basketball(page, recorder, site)
            human_pause()
            navigate_to_nba(page, recorder, site)
            human_pause()
            choose_prematch(page, recorder)
            human_pause()

            final_url = open_first_event(page, recorder, site)
            if not final_url:
                raise RuntimeError("No pre-match NBA event link was found")
            handle_consent(page, recorder)
            dismiss_overlay(page, recorder)
            human_pause()
            open_players_tab(page, recorder)
            human_pause(2.0, 4.0)

            evidence = detect_block(page, recorder)
            if evidence:
                block_evidence = evidence
                raise BlockedSite(json.dumps(evidence, ensure_ascii=False))
        except BlockedSite as exc:
            blocked = True
            block_evidence = block_evidence or {"kind": "exception", "value": str(exc)[:500]}
            try:
                recorder.screenshot(page, "blocked")
            except PWError:
                pass
        except Exception as exc:  # noqa: BLE001 - we must persist evidence for any failure
            error = f"{type(exc).__name__}: {exc}"
            try:
                recorder.screenshot(page, "error")
            except PWError:
                pass
        finally:
            try:
                final_url = final_url or page.url
            except PWError:
                pass
            recorder.close()
            context.close()
            browser.close()

    ranked = score_capture(run_dir, recorder.responses)
    write_manifest(
        run_dir, site, recorder, started_at, blocked, block_evidence, error, final_url
    )

    print("\n=== SUMMARY ===")
    print(f"run_dir: {run_dir}")
    print(f"json responses: {len(recorder.responses)}")
    print(f"live discarded: {sum(1 for item in recorder.responses if item.get('is_live'))}")
    print(f"bodies saved: {sum(1 for item in recorder.responses if item.get('body_file'))}")
    print(f"blocked: {blocked}")
    if block_evidence:
        print(f"block evidence: {json.dumps(block_evidence, ensure_ascii=False)}")
    if error:
        print(f"error: {error}")
    print("top candidates:")
    for item in ranked[:10]:
        print(
            f"  score={item['score']:>4} {item['kind']:<13} "
            f"teams={item['team_count']:>2} markets={item['market_count']:>2} "
            f"odds={item['odds_count']:>3} {item['url']}"
        )
    print(f"screenshots: {run_dir / 'screenshots'}")
    return 2 if blocked else (1 if error else 0)


def run(
    site: Site,
    headless: bool,
    session_timeout: float = SESSION_TIMEOUT_SECONDS,
) -> int:
    """Run one capture with a hard wall-clock limit."""
    with HardTimeout(session_timeout):
        return _run(site, headless)


def main() -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    parser = argparse.ArgumentParser(description="Read-only single-pass sportsbook recon")
    parser.add_argument("--site", default="betano", help="site name from sites.yaml")
    parser.add_argument(
        "--headless",
        action="store_true",
        help="run without a visible window (not used for the pilot)",
    )
    parser.add_argument(
        "--session-timeout",
        type=float,
        default=SESSION_TIMEOUT_SECONDS,
        help="hard wall-clock limit for one capture session, in seconds (default: 240)",
    )
    args = parser.parse_args()
    site = get_site(args.site)
    return run(
        site,
        headless=args.headless,
        session_timeout=args.session_timeout,
    )


if __name__ == "__main__":
    raise SystemExit(main())
