"""Tests hors ligne avec des cartes inventées, sans données de compte."""

import json
import sqlite3
from copy import deepcopy
from datetime import UTC, datetime
from unittest.mock import Mock

import httpx
import pytest

from sbc_vision.market.__main__ import import_catalog
from sbc_vision.market.database import open_database, save_cards
from sbc_vision.market.futbin import BASE_URL, Futbin, normalize


@pytest.fixture
def raw_card():
    # Ces noms et identifiants sont fictifs ; seule la structure suit la source.
    return {
        "id": {"playerCardId": {"value": 900001}},
        "baseId": {"value": 900001},
        "statsCard": {"title": "Joueur fictif"},
        "playerRating": 80,
        "position": {"value": "CM"},
        "possiblePositions": [{"position": {"value": "CM"}}, {"position": {"value": "CAM"}}],
        "clubId": {"value": 9001},
        "leagueId": {"value": 9002},
        "nationId": {"value": 9003},
        "rareType": 1,
        "isRare": True,
        "cardLevel": "GOLD",
        "untradeable": False,
        "playerStats": {"BasePace": 70},
        "price": {"ps": {"price": 800}, "pc": {"price": 0}},
        "playerLocation": {"url": "/27/player/900001/joueur-fictif"},
    }


@pytest.fixture
def db(tmp_path):
    connection = open_database(tmp_path / "catalogue.sqlite3")
    yield connection
    connection.close()


def card(raw, card_id=900001):
    raw = deepcopy(raw)
    raw["id"]["playerCardId"]["value"] = card_id
    return normalize(raw, datetime.now(UTC).isoformat())


@pytest.mark.parametrize("price", [None, 0, -1, "800", True])
def test_unknown_price_never_uses_another_market(raw_card, price):
    raw_card["price"]["pc"]["price"] = price
    result = card(raw_card)
    assert result["prices"] == {"ps": 800, "pc": None}
    assert result["positions"] == ["CM", "CAM"]


def test_versions_and_price_history_are_preserved(db, raw_card):
    original = card(raw_card)
    second_version = card(raw_card, 900002)
    save_cards(db, [original, second_version])
    updated = {**original, "observed_at": "2099-01-01T00:00:00+00:00"}
    updated["prices"] = {"ps": 900, "pc": None}
    save_cards(db, [updated])
    assert db.execute("SELECT COUNT(*) FROM cards").fetchone()[0] == 2
    assert db.execute("SELECT COUNT(*) FROM prices").fetchone()[0] == 6
    assert db.execute("SELECT credits FROM prices WHERE market='pc'").fetchone()[0] is None
    stored = db.execute("SELECT data FROM cards WHERE id=900001").fetchone()[0]
    assert json.loads(stored)["prices"]["ps"] == 900


def test_failed_database_batch_is_rolled_back(db, raw_card):
    invalid = {**card(raw_card, 900002), "name": None}
    with pytest.raises(sqlite3.IntegrityError):
        save_cards(db, [card(raw_card), invalid])
    assert db.execute("SELECT COUNT(*) FROM cards").fetchone()[0] == 0
    assert db.execute("SELECT COUNT(*) FROM prices").fetchone()[0] == 0


def test_interrupted_import_resumes_and_then_uses_cache(db, raw_card):
    source = Mock()
    source.page.side_effect = [([900001], 2), ([900002], 2)]
    source.cards.side_effect = [[card(raw_card)], ValueError("lot indisponible")]
    with pytest.raises(ValueError, match="lot indisponible"):
        import_catalog(db, source)
    assert db.execute("SELECT COUNT(*) FROM cards").fetchone()[0] == 1
    resumed = Mock()
    resumed.cards.return_value = [card(raw_card, 900002)]
    assert import_catalog(db, resumed) == 1
    resumed.page.assert_not_called()
    resumed.cards.assert_called_once_with([900002])
    cached = Mock()
    assert import_catalog(db, cached) == 0
    cached.page.assert_not_called()
    cached.cards.assert_not_called()


def test_targeted_refresh_requests_only_selected_card(db, raw_card):
    save_cards(db, [card(raw_card), card(raw_card, 900002)])
    source = Mock()
    source.cards.return_value = [card(raw_card)]
    assert import_catalog(db, source, ids=[900001, 900001], refresh=True) == 1
    source.page.assert_not_called()
    source.cards.assert_called_once_with([900001])


def test_expired_card_is_refetched(db, raw_card):
    old = {**card(raw_card), "observed_at": "2000-01-01T00:00:00+00:00"}
    save_cards(db, [old])
    source = Mock()
    source.cards.return_value = [card(raw_card)]
    assert import_catalog(db, source, ids=[900001]) == 1
    source.cards.assert_called_once_with([900001])


def test_large_selection_is_split_into_bounded_batches(db, raw_card):
    ids = list(range(900001, 900062))
    source = Mock()
    source.cards.side_effect = lambda batch: [card(raw_card, card_id) for card_id in batch]
    assert import_catalog(db, source, ids=ids) == 61
    assert [len(call.args[0]) for call in source.cards.call_args_list] == [60, 1]


def test_html_deduplication_and_last_page(monkeypatch):
    monkeypatch.setattr("sbc_vision.market.futbin.time.sleep", lambda _: None)
    html = """<table><tr class="player-row"><td>
      <a class="player-row-playercard" href="/27/player/900001/joueur-fictif">Carte</a>
      <a class="player-row-playercard" href="/27/player/900001/joueur-fictif">Carte mobile</a>
    </td></tr></table><a class="pagination-button" href="/27/players?page=4">4</a>"""
    with httpx.Client(
        base_url=BASE_URL, transport=httpx.MockTransport(lambda _: httpx.Response(200, text=html))
    ) as http:
        assert Futbin(http).page(1) == ([900001], 4)


@pytest.mark.parametrize("status", [403, 429, 503])
def test_http_error_stops_without_retry(monkeypatch, status):
    monkeypatch.setattr("sbc_vision.market.futbin.time.sleep", lambda _: None)
    handler = Mock(return_value=httpx.Response(status))
    with httpx.Client(base_url=BASE_URL, transport=httpx.MockTransport(handler)) as http:
        with pytest.raises(httpx.HTTPStatusError):
            Futbin(http).page(1)
    assert handler.call_count == 1


def test_incomplete_response_cannot_be_saved_as_success(monkeypatch):
    monkeypatch.setattr("sbc_vision.market.futbin.time.sleep", lambda _: None)
    with httpx.Client(
        base_url=BASE_URL,
        transport=httpx.MockTransport(lambda _: httpx.Response(200, json={"squadPlayerData": {}})),
    ) as http:
        with pytest.raises(ValueError, match="incomplet"):
            Futbin(http).cards([900001])


def test_requests_are_spaced_out(monkeypatch):
    sleep = Mock()
    ticks = iter([100, 100, 100.5, 102])
    monkeypatch.setattr("sbc_vision.market.futbin.time.sleep", sleep)
    monkeypatch.setattr("sbc_vision.market.futbin.time.monotonic", lambda: next(ticks))
    with httpx.Client(
        base_url=BASE_URL, transport=httpx.MockTransport(lambda _: httpx.Response(200))
    ) as http:
        source = Futbin(http)
        source.get("/test")
        source.get("/test")
    assert sleep.call_args_list[-1].args == (1.5,)
