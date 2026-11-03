"""Architecture guards for the detector package."""

from __future__ import annotations

import ast
from pathlib import Path

PACKAGE = Path(__file__).parents[1] / "surebets"
NETWORK_CLIENTS = {"aiohttp", "http.client", "httpx", "requests", "urllib.request"}
BROWSER_CLIENTS = {"playwright", "selenium"}


def imported_modules(path: Path) -> set[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    modules: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            modules.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module is not None:
            modules.add(node.module)
    return modules


def test_surebets_does_not_import_recon() -> None:
    for path in PACKAGE.rglob("*.py"):
        modules = imported_modules(path)
        assert not any(module == "recon" or module.startswith("recon.") for module in modules), path


def test_http_clients_live_only_in_net_module() -> None:
    for path in PACKAGE.rglob("*.py"):
        if path.name in ("net.py", "alerts.py"):
            continue
        assert not (imported_modules(path) & NETWORK_CLIENTS), path


def test_browser_clients_live_only_in_pinnacle_provider() -> None:
    for path in PACKAGE.rglob("*.py"):
        if path.name == "pinnacle.py":
            continue
        assert not (imported_modules(path) & BROWSER_CLIENTS), path


def test_no_bet_placement_or_login_helpers() -> None:
    forbidden = ("place_bet", "placebet", "submit_bet", "login_bookmaker", "login(")
    for path in PACKAGE.rglob("*.py"):
        text = path.read_text(encoding="utf-8").casefold()
        assert not any(token in text for token in forbidden), path
