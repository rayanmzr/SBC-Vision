"""Tests hors ligne avec des cartes inventées, sans données de compte."""

import json
import sqlite3
from copy import deepcopy
from datetime import UTC, datetime
from unittest.mock import Mock

import httpx
import pytest

from sbc_vision.sbc_engine.players import (
    BASE_URL,
    Futbin,
    import_catalog,
    normalize,
    open_database,
    save_cards,
)


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
    monkeypatch.setattr("sbc_vision.sbc_engine.players.time.sleep", lambda _: None)
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
    monkeypatch.setattr("sbc_vision.sbc_engine.players.time.sleep", lambda _: None)
    handler = Mock(return_value=httpx.Response(status))
    with httpx.Client(base_url=BASE_URL, transport=httpx.MockTransport(handler)) as http:
        with pytest.raises(httpx.HTTPStatusError):
            Futbin(http).page(1)
    assert handler.call_count == 1


def test_incomplete_response_cannot_be_saved_as_success(monkeypatch):
    monkeypatch.setattr("sbc_vision.sbc_engine.players.time.sleep", lambda _: None)
    with httpx.Client(
        base_url=BASE_URL,
        transport=httpx.MockTransport(lambda _: httpx.Response(200, json={"squadPlayerData": {}})),
    ) as http:
        with pytest.raises(ValueError, match="incomplet"):
            Futbin(http).cards([900001])


def test_requests_are_spaced_out(monkeypatch):
    sleep = Mock()
    ticks = iter([100, 100, 100.5, 102])
    monkeypatch.setattr("sbc_vision.sbc_engine.players.time.sleep", sleep)
    monkeypatch.setattr("sbc_vision.sbc_engine.players.time.monotonic", lambda: next(ticks))
    with httpx.Client(
        base_url=BASE_URL, transport=httpx.MockTransport(lambda _: httpx.Response(200))
    ) as http:
        source = Futbin(http)
        source.get("/test")
        source.get("/test")
    assert sleep.call_args_list[-1].args == (1.5,)


def test_quality_filters_have_separate_page_caches(db, raw_card):
    gold = card(raw_card)
    silver = {**card(raw_card, 900002), "card_level": "SILVER", "rating": 70}
    source = Mock()
    source.page.return_value = ([gold["id"]], 1)
    source.cards.return_value = [gold]
    assert import_catalog(db, source, pages=1) == 1
    source.page.return_value = ([silver["id"]], 1)
    source.cards.return_value = [silver]
    assert import_catalog(db, source, pages=1, quality="silver") == 1
    source.page.assert_called_with(1, quality="silver")
    rows = db.execute("SELECT quality, ids FROM pages WHERE number=1 ORDER BY quality").fetchall()
    assert [(row["quality"], json.loads(row["ids"])) for row in rows] == [
        ("all", [900001]),
        ("silver", [900002]),
    ]
    source.reset_mock()
    assert import_catalog(db, source, pages=1, quality="silver") == 0
    source.page.assert_not_called()
    source.cards.assert_not_called()


def test_old_page_index_is_migrated_without_losing_cards_or_prices(tmp_path, raw_card):
    path = tmp_path / "old.sqlite3"
    db = open_database(path)
    save_cards(db, [card(raw_card)])
    db.execute("DROP TABLE pages")
    db.execute(
        "CREATE TABLE pages (number INTEGER PRIMARY KEY, ids TEXT NOT NULL, "
        "last_page INTEGER NOT NULL)"
    )
    db.execute("INSERT INTO pages VALUES (1, '[900001]', 4)")
    db.commit()
    db.close()
    reopened = open_database(path)
    row = dict(reopened.execute("SELECT * FROM pages").fetchone())
    assert row == {"quality": "all", "number": 1, "ids": "[900001]", "last_page": 4}
    assert reopened.execute("SELECT COUNT(*) FROM cards").fetchone()[0] == 1
    assert reopened.execute("SELECT COUNT(*) FROM prices").fetchone()[0] == 2
    reopened.close()


def test_wrong_quality_from_the_provider_is_not_saved(db, raw_card):
    source = Mock()
    source.page.return_value = ([900001], 1)
    source.cards.return_value = [card(raw_card)]
    with pytest.raises(ValueError, match="qualité demandée"):
        import_catalog(db, source, quality="silver")
    assert db.execute("SELECT COUNT(*) FROM cards").fetchone()[0] == 0


def test_fresh_card_of_another_quality_does_not_hide_an_ignored_filter(db, raw_card):
    gold = card(raw_card)
    save_cards(db, [gold])
    source = Mock()
    source.page.return_value = ([900001], 1)
    source.cards.return_value = [gold]
    with pytest.raises(ValueError, match="qualité demandée"):
        import_catalog(db, source, quality="silver")
    source.cards.assert_called_once_with([900001])


def test_invalid_quality_is_rejected_before_any_request(db):
    source = Mock()
    with pytest.raises(ValueError, match="qualité valide"):
        import_catalog(db, source, quality="unknown")
    source.page.assert_not_called()
    source.cards.assert_not_called()


def test_quality_filter_is_sent_in_the_public_list_request(monkeypatch):
    monkeypatch.setattr("sbc_vision.sbc_engine.players.time.sleep", lambda _: None)

    def handler(request):
        assert request.url.params["page"] == "2"
        assert request.url.params["version"] == "bronze"
        return httpx.Response(
            200,
            text='<tr class="player-row"><td><a class="player-row-playercard" '
            'href="/27/player/900001/test">Carte</a></td></tr>',
        )

    with httpx.Client(base_url=BASE_URL, transport=httpx.MockTransport(handler)) as http:
        assert Futbin(http).page(2, quality="bronze")[0] == [900001]
