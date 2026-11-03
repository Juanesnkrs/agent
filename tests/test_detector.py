from datetime import datetime, timedelta, timezone

import pytest

from surebets.alerts import RULES, WARNING, format_alert, send_telegram
from surebets.cli import Config, scan
from surebets.errors import ProviderBlockedError, ProviderUnavailableError
from surebets.filters import prematch_filter
from surebets.matching import find_opportunities
from surebets.models import OddsQuote
from surebets.providers.base import OddsProvider
from surebets.providers.piwi import PiwiProvider
from surebets.store import OpportunityStore

NOW = datetime(2026, 11, 2, 18, 0, tzinfo=timezone.utc)
START = NOW + timedelta(hours=5)


def q(book, market, sel, odds, line=None, player=None, swap=False, start=START, at=NOW, eid="e"):
    home, away = ("Miami Heat", "LAL Lakers") if swap else ("Los Angeles Lakers", "Miami Heat")
    if swap and sel in ("home", "away"):
        sel = "away" if sel == "home" else "home"
    if swap and sel.startswith(("home_", "away_")):
        sel = ("away_" if sel.startswith("home_") else "home_") + sel.split("_")[1]
    return OddsQuote(eid, home, away, start, market, line, sel, book, odds, at, player)


def book_a():
    return [
        q("A", "moneyline", "home", 2.30), q("A", "moneyline", "away", 1.60),
        q("A", "total", "over", 2.10, 220.5), q("A", "total", "under", 1.70, 220.5),
        q("A", "handicap", "home", 2.10, -4.5), q("A", "handicap", "away", 1.70, 4.5),
        q("A", "player_points", "over", 2.10, 25.5, "Luka Dončić"),
        q("A", "player_points", "under", 1.70, 25.5, "Luka Dončić"),
        q("A", "team_total", "home_over", 2.10, 110.5), q("A", "team_total", "home_under", 1.70, 110.5),
    ]


def book_b(**kw):
    return [
        q("B", "moneyline", "home", 1.60, **kw), q("B", "moneyline", "away", 2.30, **kw),
        q("B", "total", "over", 1.70, 220.5, **kw), q("B", "total", "under", 2.10, 220.5, **kw),
        q("B", "handicap", "home", 1.70, -4.5, **kw), q("B", "handicap", "away", 2.10, 4.5, **kw),
        q("B", "player_points", "over", 1.70, 25.5, "Luka Doncic", **kw),
        q("B", "player_points", "under", 2.10, 25.5, "Luka Doncic", **kw),
        q("B", "team_total", "home_over", 1.70, 110.5, **kw), q("B", "team_total", "home_under", 2.10, 110.5, **kw),
    ]


@pytest.mark.parametrize("swap", [False, True])
def test_every_market_type_is_detected(swap):
    markets = {o.market for o in find_opportunities(book_a(), book_b(swap=swap))}
    assert markets == {"moneyline", "handicap", "total", "team_total", "player_points"}


def test_no_arbitrage_when_prices_are_fair():
    a = [q("A", "moneyline", "home", 1.90), q("A", "moneyline", "away", 1.90)]
    b = [q("B", "moneyline", "home", 1.90), q("B", "moneyline", "away", 1.90)]
    assert find_opportunities(a, b) == []


def test_same_bookmaker_is_never_paired():
    assert find_opportunities(book_a(), [x for x in book_a()]) == []


def test_different_lines_are_not_paired():
    a = [q("A", "total", "over", 2.2, 220.5), q("A", "total", "under", 1.5, 220.5)]
    b = [q("B", "total", "over", 1.5, 221.5), q("B", "total", "under", 2.2, 221.5)]
    assert find_opportunities(a, b) == []


def test_handicap_requires_opposite_line():
    a = [q("A", "handicap", "home", 2.2, -4.5)]
    b = [q("B", "handicap", "away", 2.2, 5.5)]
    assert find_opportunities(a, b) == []


def test_events_more_than_ten_minutes_apart_are_not_matched():
    late = START + timedelta(minutes=11)
    assert find_opportunities(book_a(), book_b(start=late)) == []


def test_net_roi_applies_commission():
    opp = find_opportunities(book_a(), book_b())[0]
    assert opp.net_roi({"a": 0.05, "b": 0.05}) < opp.roi


def test_prematch_filter_drops_started_and_stale():
    quotes = [
        q("A", "moneyline", "home", 2.0),
        q("A", "moneyline", "away", 2.0, start=NOW + timedelta(minutes=10)),
        q("A", "moneyline", "home", 2.0, at=NOW - timedelta(minutes=30)),
    ]
    kept, stats = prematch_filter(quotes, NOW)
    assert len(kept) == 1 and stats == {"too_close_or_started": 1, "stale": 1}


def test_alert_text_has_warnings_and_stakes():
    opp = find_opportunities(book_a(), book_b())[0]
    text = format_alert(opp, NOW, max_stake=100)
    assert WARNING in text and "inicia en 5h" in text and "neto" in text
    if opp.market != "moneyline":
        assert RULES in text


def test_telegram_without_credentials_does_not_call_network(capsys):
    class Boom:
        def post(self, *a, **k):
            raise AssertionError("network used")

    assert send_telegram("hola", None, None, client=Boom()) is False
    assert "hola" in capsys.readouterr().out


def test_store_requires_persistence_and_improvement(tmp_path):
    store = OpportunityStore(tmp_path)
    opp = find_opportunities(book_a(), book_b())[0]
    assert store.update([(opp, 0.04)], NOW, persistence_n=2) == []
    assert store.update([(opp, 0.04)], NOW, persistence_n=2) == [opp]
    assert store.update([(opp, 0.04)], NOW, persistence_n=2) == []
    assert store.update([(opp, 0.06)], NOW, persistence_n=2) == [opp]
    assert (tmp_path / "opportunities.jsonl").read_text().count("\n") == 4


def test_piwi_never_fabricates_odds(monkeypatch):
    provider = PiwiProvider()
    with pytest.raises(ProviderUnavailableError):
        provider.parse_payload({"n": [[4, "Basketball", [[487, "NBA", [[1, "A", "B"]]]]]]}, NOW)
    monkeypatch.setattr(provider, "capture_raw", lambda: [{"n": []}])
    with pytest.raises(ProviderUnavailableError):
        provider.fetch_odds()


class Fake(OddsProvider):
    def __init__(self, quotes=None, error=None):
        self.quotes, self.error = quotes, error

    def fetch_odds(self):
        if self.error:
            raise self.error
        return self.quotes


def test_scan_alerts_and_survives_provider_failures(tmp_path):
    cfg = Config(persistence_n=1)
    sent: list[str] = []
    store = OpportunityStore(tmp_path)
    alerts = scan([Fake(book_a()), Fake(book_b())], NOW, cfg, store, sent.append)
    assert alerts and sent == alerts
    assert scan([Fake(book_a()), Fake(error=ProviderBlockedError("x"))], NOW, cfg, store, sent.append) == []
