"""Tests hors ligne : cartes inventées et protocole enregistré avec valeurs anonymisées."""

import json
import sqlite3
from copy import deepcopy
from datetime import UTC, datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import Mock

import httpx
import pytest

from sbc_vision.sbc_engine.players import (
    BASE_URL,
    Futbin,
    import_catalog,
    import_file,
    import_readings,
    list_items,
    normalize,
    open_database,
    save_cards,
    save_page,
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


def test_catalogue_preserves_short_names_and_supports_old_responses(raw_card):
    assert card(raw_card)["aliases"] == []
    raw_card["playerName"] = " Fictif "
    raw_card["statsCard"]["cardname"] = "Fictif"
    result = card(raw_card)
    assert result["name"] == "Joueur fictif"
    assert result["aliases"] == ["Fictif"]


@pytest.mark.parametrize("aliases", ["Fictif", None, [""], [42]])
def test_invalid_name_aliases_in_an_export_do_not_enter_the_catalogue(
    db, raw_card, tmp_path, aliases
):
    path = tmp_path / "catalogue.json"
    path.write_text(json.dumps({"cards": [{**card(raw_card), "aliases": aliases}]}))
    with pytest.raises(ValueError, match="alias"):
        import_file(db, path)
    assert db.execute("SELECT COUNT(*) FROM cards").fetchone()[0] == 0


@pytest.mark.parametrize(
    "update",
    [
        {"club_id": -1},
        {"card_level": "PLATINUM"},
        {"item_score": True},
        {"market_quantity": 0},
        {"chemistry_kind": "unknown"},
        {"observed_at": "2026-11-13T12:00:00"},
    ],
)
def test_invalid_optional_export_data_rejects_the_whole_file(db, raw_card, tmp_path, update):
    path = tmp_path / "catalogue.json"
    path.write_text(json.dumps({"cards": [card(raw_card), {**card(raw_card, 900002), **update}]}))
    with pytest.raises(ValueError):
        import_file(db, path)
    assert db.execute("SELECT COUNT(*) FROM cards").fetchone()[0] == 0
    assert db.execute("SELECT COUNT(*) FROM prices").fetchone()[0] == 0


def test_offline_export_preserves_original_dates_and_unknown_prices(db, tmp_path):
    fixture = json.loads(
        (Path(__file__).parents[1] / "data/fixtures/club.synthetic.json").read_text()
    )
    path = tmp_path / "catalogue.json"
    path.write_text(json.dumps({"cards": fixture["catalogue"]}))
    assert import_file(db, path) == 3
    stored = {r["id"]: json.loads(r["data"]) for r in db.execute("SELECT id,data FROM cards")}
    assert [stored[c["id"]]["observed_at"] for c in fixture["catalogue"]] == [
        c["observed_at"] for c in fixture["catalogue"]
    ]
    assert stored[900002]["prices"]["pc"] is None
    assert db.execute("SELECT COUNT(*) FROM prices").fetchone()[0] == 6
    assert list_items(db) == []


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
    assert row == {
        "quality": "all",
        "number": 1,
        "ids": "[900001]",
        "last_page": 4,
        "observed_at": None,
    }
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


@pytest.mark.parametrize("empty", [False, True])
def test_name_search_uses_the_public_filter_and_recognizes_an_empty_table(monkeypatch, empty):
    monkeypatch.setattr("sbc_vision.sbc_engine.players.time.sleep", lambda _: None)

    def handler(request):
        assert dict(request.url.params) == {"page": "1", "search": "Fictif"}
        row = (
            ""
            if empty
            else (
                '<tr class="player-row"><td><a class="player-row-playercard" '
                'href="/27/player/900001/test">Fictif</a></td></tr>'
            )
        )
        return httpx.Response(
            200, text=f'<table class="players-table"><tbody>{row}</tbody></table>'
        )

    with httpx.Client(base_url=BASE_URL, transport=httpx.MockTransport(handler)) as http:
        assert Futbin(http).page(1, search="Fictif") == ([] if empty else [900001], 1)


def test_name_search_never_treats_an_unrecognized_page_as_an_empty_result(monkeypatch):
    monkeypatch.setattr("sbc_vision.sbc_engine.players.time.sleep", lambda _: None)
    with httpx.Client(
        base_url=BASE_URL,
        transport=httpx.MockTransport(lambda _: httpx.Response(200, text="<p>Connexion</p>")),
    ) as http:
        with pytest.raises(ValueError, match="format FUTBIN"):
            Futbin(http).page(1, search="Fictif")


def reading_report():
    return {
        "capture_id": "synthetic",
        "cards": [
            {
                "element_id": "card-1",
                "issues": [],
                "reading": {
                    "capture_id": "synthetic",
                    "element_id": "card-1",
                    "name": "Fictif@)",
                    "rating": 80,
                    "confidence": 0.99,
                },
            },
            {"element_id": "bad", "issues": ["Note incertaine"], "reading": None},
        ],
    }


def test_ocr_lookup_fetches_versions_without_creating_owned_cards_or_polluting_pages(db, raw_card):
    raw_card["playerName"] = "Fictif"
    source = Mock()
    source.page.side_effect = [([900001], 2), ([900002], 2)]
    source.cards.return_value = [card(raw_card), card(raw_card, 900002)]
    report = import_readings(db, source, reading_report())
    assert report["cards"][0]["candidate_ids"] == [900001, 900002]
    assert report["cards"][0]["needs_confirmation"] is True
    assert report["cards"][1]["candidate_ids"] == []
    assert report["imported"] == 2 and report["catalogue_searches"][0]["complete"] is True
    assert source.page.call_args_list == [
        ((1,), {"search": "Fictif"}),
        ((2,), {"search": "Fictif"}),
    ]
    assert list_items(db) == []
    assert db.execute("SELECT COUNT(*) FROM pages").fetchone()[0] == 0
    source.reset_mock()
    cached = import_readings(db, source, report)
    source.page.assert_not_called()
    source.cards.assert_not_called()
    assert cached["imported"] == 0


def test_bounded_lookup_marks_truncation_and_updates_missing_aliases(db, raw_card):
    save_cards(db, [card(raw_card)])
    raw_card["playerName"] = "Fictif"
    source = Mock()
    source.page.return_value = ([900001], 3)
    source.cards.return_value = [card(raw_card)]
    result = import_readings(db, source, reading_report(), pages=1)
    assert result["cards"][0]["candidate_ids"] == [900001]
    assert result["catalogue_searches"] == [{"name": "Fictif", "pages": 1, "complete": False}]
    assert result["imported"] == 1
    source.page.assert_called_once()


def test_empty_lookup_never_falls_back_to_importing_the_whole_index(db):
    source = Mock()
    source.page.return_value = ([], 1)
    result = import_readings(db, source, reading_report())
    assert result["cards"][0]["candidate_ids"] == [] and result["imported"] == 0
    source.page.assert_called_once_with(1, search="Fictif")
    source.cards.assert_not_called()


def test_repeated_search_page_stops_before_downloading_wrong_versions(db):
    source = Mock()
    source.page.return_value = ([900001], 3)
    with pytest.raises(ValueError, match="répète"):
        import_readings(db, source, reading_report())
    source.cards.assert_not_called()
    assert list_items(db) == []


def test_lookup_rejects_a_synthetic_database_before_any_request(db, raw_card):
    save_cards(db, [{**card(raw_card), "source_url": "urn:sbc-vision:synthetic:900001"}])
    source = Mock()
    with pytest.raises(ValueError, match="base séparée"):
        import_readings(db, source, reading_report())
    source.page.assert_not_called()
    source.cards.assert_not_called()


@pytest.mark.parametrize("count", [1, 2])
def test_lookup_cli_writes_a_report_without_confirming_inventory(
    tmp_path, monkeypatch, raw_card, capsys, count
):
    from sbc_vision.sbc_engine.__main__ import main

    raw_card["playerName"] = "Fictif"
    source = Mock()
    ids = list(range(900001, 900001 + count))
    source.page.return_value = (ids, 1)
    source.cards.return_value = [card(raw_card, i) for i in ids]
    monkeypatch.setattr("sbc_vision.sbc_engine.__main__.Futbin", lambda *_: source)
    reading, output = tmp_path / "reading.json", tmp_path / "matches.json"
    reading.write_text(json.dumps(reading_report()))
    assert (
        main(
            [
                "import",
                "--reading",
                str(reading),
                "--output",
                str(output),
                "--db",
                str(tmp_path / "catalogue.sqlite3"),
            ]
        )
        == 0
    )
    assert json.loads(output.read_text())["cards"][0]["candidate_ids"] == ids
    assert ("Version ambiguë" in capsys.readouterr().out) is (count == 2)


@pytest.mark.parametrize(
    "observed", [None, "2000-01-01T00:00:00+00:00", "2099-01-01T00:00:00+00:00"]
)
def test_stale_or_undated_page_is_rediscovered_without_losing_cached_cards(db, raw_card, observed):
    save_cards(db, [card(raw_card)])
    save_page(db, 1, [900001], 1)
    db.execute("UPDATE pages SET observed_at=?", (observed,))
    db.commit()
    source = Mock()
    source.page.return_value = ([900002], 1)
    source.cards.return_value = [card(raw_card, 900002)]
    assert import_catalog(db, source, pages=1) == 1
    source.page.assert_called_once_with(1, quality="all")
    source.cards.assert_called_once_with([900002])
    assert db.execute("SELECT COUNT(*) FROM cards").fetchone()[0] == 2
    assert db.execute("SELECT COUNT(*) FROM prices").fetchone()[0] == 4


@pytest.mark.parametrize(
    "age, offset, fresh", [(1, 14, True), (23, -12, True), (25, 14, False), (-48, 0, False)]
)
def test_card_cache_compares_instants_instead_of_timezone_strings(db, raw_card, age, offset, fresh):
    observed = (datetime.now(UTC) - timedelta(hours=age)).astimezone(
        timezone(timedelta(hours=offset))
    )
    save_cards(db, [{**card(raw_card), "observed_at": observed.isoformat()}])
    source = Mock()
    source.cards.return_value = [card(raw_card)]
    assert import_catalog(db, source, ids=[900001]) == (0 if fresh else 1)
    assert source.cards.called is not fresh
    source.page.assert_not_called()


def test_zero_cache_age_refreshes_both_index_and_card_data(db, raw_card):
    save_cards(db, [card(raw_card)])
    save_page(db, 1, [900001], 1)
    source = Mock()
    source.page.return_value = ([900001], 1)
    source.cards.return_value = [card(raw_card)]
    assert import_catalog(db, source, pages=1, max_age=0) == 1
    source.page.assert_called_once_with(1, quality="all")
    source.cards.assert_called_once_with([900001])


@pytest.mark.parametrize("max_age", [-1, float("nan"), float("inf")])
def test_invalid_cache_age_is_rejected_before_any_request(db, max_age):
    source = Mock()
    with pytest.raises(ValueError, match="cache finie"):
        import_catalog(db, source, max_age=max_age)
    source.page.assert_not_called()
    source.cards.assert_not_called()


def test_quality_page_cache_migration_keeps_prices_and_forces_rediscovery(tmp_path, raw_card):
    path = tmp_path / "previous.sqlite3"
    old = open_database(path)
    save_cards(old, [card(raw_card)])
    old.execute("DROP TABLE pages")
    old.execute(
        "CREATE TABLE pages (quality TEXT, number INTEGER, ids TEXT, last_page INTEGER, "
        "PRIMARY KEY(quality, number))"
    )
    old.execute("INSERT INTO pages VALUES ('all',1,'[900001]',1)")
    old.commit()
    old.close()
    db = open_database(path)
    source = Mock()
    source.page.return_value = ([900001], 1)
    assert import_catalog(db, source, pages=1) == 0
    source.page.assert_called_once_with(1, quality="all")
    source.cards.assert_not_called()
    assert db.execute("SELECT COUNT(*) FROM prices").fetchone()[0] == 2
    db.close()


def test_recorded_public_protocol_replays_offline_with_synthetic_values(db, monkeypatch):
    fixture = json.loads(
        (Path(__file__).parents[1] / "data/fixtures/futbin.recorded.synthetic.json").read_text()
    )
    assert fixture["data_kind"] == "sanitized_public_recording"
    monkeypatch.setattr("sbc_vision.sbc_engine.players.time.sleep", lambda _: None)
    requests = []

    def handler(request):
        requests.append(request)
        if request.url.path == "/27/players":
            assert dict(request.url.params) == {"page": "1", "search": "Exemple"}
            return httpx.Response(200, text=fixture["index_html"])
        assert request.url.path == "/siteapi/27/get-squad"
        assert request.url.params.get_list("playerCardIds") == ["900001", "900002"]
        return httpx.Response(200, json=fixture["cards_response"])

    report = reading_report()
    report["cards"][0]["reading"]["name"] = "Exemple"
    with httpx.Client(base_url=BASE_URL, transport=httpx.MockTransport(handler)) as http:
        source = Futbin(http)
        result = import_readings(db, source, report)
        assert result["imported"] == 2
        assert result["cards"][0]["candidate_ids"] == [900001]
        result = import_readings(db, source, result)
        assert result["imported"] == 0 and len(requests) == 2
    cards = {r["id"]: json.loads(r["data"]) for r in db.execute("SELECT id,data FROM cards")}
    assert cards[900001]["positions"] == ["GK"]
    assert cards[900001]["prices"] == {"ps": 800, "pc": 1000}
    assert cards[900002]["prices"] == {"ps": 900, "pc": None}
    assert cards[900001]["nation_name"] == "Pays fictif"
    assert cards[900002]["chemistry_kind"] == "unsupported"
    assert db.execute("SELECT COUNT(*) FROM prices").fetchone()[0] == 4
    assert list_items(db) == []
