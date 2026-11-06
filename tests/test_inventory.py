"""Versions proches, doubles observations et protections, avec un club fictif."""

import json
import sqlite3
from pathlib import Path

import pytest
from pydantic import ValidationError

from sbc_vision.sbc_engine.__main__ import main
from sbc_vision.sbc_engine.catalogue import open_database, save_cards
from sbc_vision.sbc_engine.inventory import (
    find_candidates,
    list_items,
    save_item,
    set_protected,
)
from sbc_vision.sbc_engine.models import CardReading, ClubItem

FIXTURE = Path(__file__).resolve().parents[1] / "data/fixtures/club.synthetic.json"


@pytest.fixture
def fixture():
    return json.loads(FIXTURE.read_text())


@pytest.fixture
def db(tmp_path, fixture):
    connection = open_database(tmp_path / "club.sqlite3")
    save_cards(connection, fixture["catalogue"])
    yield connection
    connection.close()


def populate(db, fixture):
    for raw in fixture["items"]:
        save_item(db, ClubItem.model_validate(raw), confirmed=True)


def test_similar_versions_remain_ambiguous_and_do_not_add_items(db, fixture):
    reading = CardReading.model_validate(fixture["readings"][0])
    reading = reading.model_copy(update={"name": "ÁLEX-EXEMPLE"})
    assert [card["id"] for card in find_candidates(db, reading)] == [900001, 900002]
    assert list_items(db) == []


def test_nonrare_filter_is_not_ignored_when_false(db, fixture):
    reading = CardReading.model_validate(fixture["readings"][1])
    assert [card["id"] for card in find_candidates(db, reading)] == [900001]
    assert list_items(db) == []


@pytest.mark.parametrize("update", [{"rating": 90}, {"position": "GK"}, {"club_id": 9999}])
def test_incompatible_readings_have_no_candidate(db, fixture, update):
    reading = CardReading.model_validate({**fixture["readings"][0], **update})
    assert find_candidates(db, reading) == []


def test_quantity_counts_copies_and_keeps_protection_per_copy(db, fixture):
    populate(db, fixture)
    items = list_items(db)
    assert len(items) == 3
    assert [item["card_id"] for item in items].count(900001) == 2
    assert [item["instance_id"] for item in list_items(db, unprotected_only=True)] == [
        "demo-002",
        "demo-003",
    ]
    assert items[0]["tradeable"] is False
    assert items[2]["tradeable"] is None


def test_new_observation_preserves_quantity_protection_and_tradeability(db, fixture):
    populate(db, fixture)
    reread = ClubItem(instance_id="demo-001", card_id=900001, source_observation="other-screen:1")
    save_item(db, reread, confirmed=True)
    items = list_items(db)
    assert len(items) == 3
    assert items[0]["protected"] is True
    assert items[0]["tradeable"] is False
    assert items[0]["source_observation"] == "other-screen:1"


def test_one_instance_cannot_silently_change_version(db, fixture):
    populate(db, fixture)
    changed = ClubItem(instance_id="demo-001", card_id=900002, source_observation="screen:2")
    with pytest.raises(ValueError, match="autre version"):
        save_item(db, changed, confirmed=True)
    assert list_items(db)[0]["card_id"] == 900001


def test_unconfirmed_item_is_never_inserted(db, fixture):
    with pytest.raises(ValueError, match="Confirmer"):
        save_item(db, ClubItem.model_validate(fixture["items"][0]))
    assert list_items(db) == []


def test_unknown_catalogue_version_cannot_enter_inventory(db):
    item = ClubItem(instance_id="unknown", card_id=999999, source_observation="screen:1")
    with pytest.raises(sqlite3.IntegrityError):
        save_item(db, item, confirmed=True)
    assert list_items(db) == []


def test_protection_can_be_changed_and_survives_reopening(tmp_path, fixture):
    path = tmp_path / "persistent.sqlite3"
    with open_database(path) as db:
        save_cards(db, fixture["catalogue"])
        populate(db, fixture)
        set_protected(db, "demo-002", True)
    db.close()
    with open_database(path) as reopened:
        assert [item["instance_id"] for item in list_items(reopened, unprotected_only=True)] == [
            "demo-003"
        ]
        set_protected(reopened, "demo-001", False)
        assert len(list_items(reopened, unprotected_only=True)) == 2
        with pytest.raises(ValueError, match="introuvable"):
            set_protected(reopened, "does-not-exist", True)
    reopened.close()


@pytest.mark.parametrize("update", [{"card_id": 0}, {"protected": "false"}, {"instance_id": " "}])
def test_malformed_items_are_rejected(fixture, update):
    with pytest.raises(ValidationError):
        ClubItem.model_validate({**fixture["items"][0], **update})


@pytest.mark.parametrize("update", [{"rating": 83.5}, {"confidence": 1.1}, {"unknown": "field"}])
def test_malformed_readings_are_rejected(fixture, update):
    with pytest.raises(ValidationError):
        CardReading.model_validate({**fixture["readings"][0], **update})


def test_demo_relaunch_does_not_duplicate_items(tmp_path, capsys):
    path = str(tmp_path / "demo.sqlite3")
    assert main(["club", "--db", path, "demo"]) == 0
    assert main(["club", "--db", path, "demo"]) == 0
    assert main(["club", "--db", path, "list", "--unprotected"]) == 0
    assert "2 exemplaires affichés" in capsys.readouterr().out
    assert main(["club", "--db", path, "protect", "demo-002"]) == 0
    with open_database(path) as db:
        assert len(list_items(db)) == 3
        assert len(list_items(db, unprotected_only=True)) == 1
    db.close()


def test_demo_refuses_to_mix_with_real_catalogue(tmp_path, fixture):
    path = tmp_path / "market.sqlite3"
    real_source = {**fixture["catalogue"][0], "source_url": "https://www.futbin.com/27/player/1"}
    with open_database(path) as db:
        save_cards(db, [real_source])
    db.close()
    assert main(["club", "--db", str(path), "demo"]) == 1
    with open_database(path) as db:
        assert db.execute("SELECT COUNT(*) FROM cards").fetchone()[0] == 1
        assert list_items(db) == []
    db.close()
