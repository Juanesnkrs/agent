"""Load verified site metadata from sites.yaml."""

from dataclasses import dataclass
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
SITES_PATH = ROOT / "sites.yaml"

REQUIRED_FIELDS = {
    "name",
    "display_name",
    "base_url",
    "country",
    "license",
    "http_check",
}


@dataclass(frozen=True)
class Site:
    """One verified sportsbook."""

    name: str
    display_name: str
    base_url: str
    country: str
    license: dict
    http_check: dict
    notes: str = ""
    doubts: str = ""
    provider: dict | None = None
    capture: dict | None = None
    navigation: dict | None = None

    @property
    def raw_dir(self) -> Path:
        return ROOT / "recon" / "raw" / self.name


def load_sites(path: Path | str = SITES_PATH) -> dict[str, Site]:
    """Return sites keyed by their short name, validating the YAML shape."""
    data = yaml.safe_load(Path(path).read_text(encoding="utf-8"))
    if not isinstance(data, dict) or not isinstance(data.get("sites"), list):
        raise ValueError("sites.yaml must contain a top-level 'sites' list")

    sites: dict[str, Site] = {}
    for entry in data["sites"]:
        missing = REQUIRED_FIELDS - set(entry)
        if missing:
            raise ValueError(f"site entry missing fields: {sorted(missing)}")
        if entry["name"] in sites:
            raise ValueError(f"duplicate site name: {entry['name']}")
        if not str(entry["base_url"]).startswith("https://"):
            raise ValueError(f"{entry['name']}: base_url must use https")
        sites[entry["name"]] = Site(
            name=entry["name"],
            display_name=entry["display_name"],
            base_url=entry["base_url"],
            country=entry["country"],
            license=entry["license"],
            http_check=entry["http_check"],
            notes=entry.get("notes", ""),
            doubts=entry.get("doubts", ""),
            provider=entry.get("provider"),
            capture=entry.get("capture"),
            navigation=entry.get("navigation"),
        )
    return sites


def get_site(name: str, path: Path | str = SITES_PATH) -> Site:
    """Return one site or raise a helpful error."""
    sites = load_sites(path)
    try:
        return sites[name]
    except KeyError:
        raise KeyError(f"unknown site '{name}'; known: {', '.join(sorted(sites))}") from None
