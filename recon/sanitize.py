"""Privacy helpers used when recording network traffic."""

from __future__ import annotations

import re
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

SENSITIVE_QUERY = re.compile(
    r"(token|auth|session|sess|jwt|key|api[-_]?key|sig|signature|expires|policy|"
    r"credential|password|secret|nonce|csrf)",
    re.IGNORECASE,
)

# Response headers that are safe to keep as evidence. Everything else
# (Set-Cookie, Authorization, etc.) is dropped.
SAFE_RESPONSE_HEADERS = {
    "cache-control",
    "content-encoding",
    "content-length",
    "content-type",
    "date",
    "etag",
    "last-modified",
    "server",
    "vary",
    "x-cache",
    "x-request-id",
}

SECRET_VALUE = re.compile(r"^[A-Za-z0-9._~+/=-]+$")
LIVE_SEGMENT = re.compile(r"^live$", re.IGNORECASE)


def _looks_like_secret(value: str) -> bool:
    """Heuristic for opaque query values that should not be persisted."""
    if len(value) < 24 or value.isdigit():
        return False
    if not SECRET_VALUE.fullmatch(value):
        return False
    has_upper = bool(re.search(r"[A-Z]", value))
    has_lower = bool(re.search(r"[a-z]", value))
    return (has_upper and has_lower) or len(value) >= 40


def redact_url(url: str) -> str:
    """Redact token-like query parameters while preserving the route."""
    parts = urlsplit(url)
    if not parts.query:
        return url
    pairs: list[tuple[str, str]] = []
    for key, value in parse_qsl(parts.query, keep_blank_values=True):
        if SENSITIVE_QUERY.search(key) or _looks_like_secret(value):
            value = "REDACTED"
        pairs.append((key, value))
    query = urlencode(pairs, doseq=True)
    return urlunsplit((parts.scheme, parts.netloc, parts.path, query, parts.fragment))


def safe_headers(headers: dict[str, str]) -> dict[str, str]:
    """Keep only non-sensitive response headers."""
    return {
        key.lower(): value
        for key, value in headers.items()
        if key.lower() in SAFE_RESPONSE_HEADERS
    }


def is_live_url(url: str) -> bool:
    """True for live-betting endpoints, but not for /livecasino/."""
    path = urlsplit(url).path
    return any(LIVE_SEGMENT.fullmatch(part) for part in path.split("/") if part)


def slugify(value: str, max_length: int = 70) -> str:
    """Make a filesystem-safe ASCII slug."""
    value = value.lower().strip()
    value = re.sub(r"[^a-z0-9]+", "-", value)
    value = re.sub(r"-{2,}", "-", value).strip("-")
    return (value or "response")[:max_length].strip("-")
