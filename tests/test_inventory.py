"""Versions proches, doubles observations et protections, avec un club fictif."""

import json
import sqlite3
from pathlib import Path

import pytest
from pydantic import ValidationError

from sbc_vision.sbc_engine.__main__ import main
from sbc_vision.sbc_engine.models import CardReading, ClubItem
from sbc_vision.sbc_engine.players import (
    confirm_readings,
    find_candidates,
    list_items,
    open_database,
    save_cards,
    save_item,
    set_protected,
)

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


@pytest.fixture
def ocr_report(fixture):
    return {
        "capture_id": "demo-screen",
        "cards": [
            {"element_id": r["element_id"], "reading": r, "issues": [], "candidate_ids": []}
            for r in fixture["readings"]
        ],
    }


def test_confirmed_ocr_batch_distinguishes_versions_and_preserves_copies(db, ocr_report):
    ocr_report["cards"][0]["reading"]["item_score"] = 410
    choices = {
        "card-1": {"instance_id": "copy-rare", "card_id": 900002, "protected": True},
        "card-2": {"instance_id": "copy-normal", "card_id": 900001},
    }
    assert confirm_readings(db, ocr_report, choices, confirmed=True) == 2
    items = {item["instance_id"]: item for item in list_items(db)}
    assert items["copy-rare"]["card_id"] == 900002
    assert items["copy-rare"]["item_score"] == 410
    assert items["copy-rare"]["protected"] is True

    # Une autre capture revoit les mêmes exemplaires, sans effacer leurs informations.
    ocr_report["capture_id"] = "another-screen"
    for card in ocr_report["cards"]:
        card["reading"]["capture_id"] = "another-screen"
        card["reading"]["item_score"] = None
    choices["card-1"]["protected"] = False
    assert confirm_readings(db, ocr_report, choices, confirmed=True) == 2
    items = {item["instance_id"]: item for item in list_items(db)}
    assert len(items) == 2
    assert items["copy-rare"]["protected"] is True
    assert items["copy-rare"]["item_score"] == 410
    assert items["copy-rare"]["source_observation"] == "another-screen:card-1"


@pytest.mark.parametrize("problem", ["unreadable", "warning", "capture", "element", "version"])
def test_invalid_ocr_selection_never_enters_inventory(db, ocr_report, problem):
    card = ocr_report["cards"][0]
    choice = {"instance_id": "copy-1", "card_id": 900001}
    if problem == "unreadable":
        card["reading"] = None
    elif problem == "warning":
        card["issues"] = ["Item Score à relire."]
    elif problem in {"capture", "element"}:
        card["reading"][f"{problem}_id"] = "wrong"
    else:
        choice["card_id"] = 900003
        card["candidate_ids"] = [900003]  # La liste fournie n'est pas une preuve.
    with pytest.raises(ValueError):
        confirm_readings(db, ocr_report, {"card-1": choice}, confirmed=True)
    assert list_items(db) == []


def test_one_physical_copy_cannot_count_twice_in_a_batch(db, ocr_report):
    choices = {key: {"instance_id": "same-copy", "card_id": 900001} for key in ("card-1", "card-2")}
    with pytest.raises(ValueError, match="distincts"):
        confirm_readings(db, ocr_report, choices, confirmed=True)
    assert list_items(db) == []


def test_late_version_conflict_rolls_back_the_entire_batch(db, fixture, ocr_report):
    populate(db, fixture)
    before = list_items(db)
    ocr_report["cards"][1]["reading"].pop("is_rare")
    choices = {
        "card-1": {"instance_id": "new-copy", "card_id": 900002},
        "card-2": {"instance_id": "demo-001", "card_id": 900002},
    }
    with pytest.raises(ValueError, match="autre version"):
        confirm_readings(db, ocr_report, choices, confirmed=True)
    assert list_items(db) == before


def test_sync_cli_requires_confirmation_and_can_import_only_selected_readings(
    db, ocr_report, tmp_path
):
    report, choices = tmp_path / "ocr.json", tmp_path / "choices.json"
    # Une lecture illisible non sélectionnée ne bloque pas la carte vérifiée.
    ocr_report["cards"][1]["reading"] = None
    report.write_text(json.dumps(ocr_report))
    choices.write_text(json.dumps({"card-1": {"instance_id": "copy-1", "card_id": 900001}}))
    path = db.execute("PRAGMA database_list").fetchone()[2]
    args = ["club", "--db", path, "sync", str(report), str(choices)]
    assert main(args) == 1
    assert list_items(db) == []
    assert main(args + ["--confirm"]) == 0
    assert main(args + ["--confirm"]) == 0
    assert len(list_items(db)) == 1


def test_similar_versions_remain_ambiguous_and_do_not_add_items(db, fixture):
    reading = CardReading.model_validate(fixture["readings"][0])
    reading = reading.model_copy(update={"name": "ÁLEX-EXEMPLE"})
    assert [card["id"] for card in find_candidates(db, reading)] == [900001, 900002]
    assert list_items(db) == []


def test_short_name_keeps_all_versions_until_explicit_confirmation(db, fixture, ocr_report):
    # Plusieurs joueurs et versions partagent un nom court : aucun choix automatique.
    for card in fixture["catalogue"][:2]:
        card.update(name="Alex Exemple Complet", aliases=["Exemple"])
    fixture["catalogue"][2].update(
        name="Mina Exemple", rating=83, positions=["CM"], aliases=["Exemple"]
    )
    save_cards(db, fixture["catalogue"])
    raw = ocr_report["cards"][0]["reading"]
    raw["name"] = "ÉXEMPLE@)"
    reading = CardReading.model_validate(raw)
    assert [c["id"] for c in find_candidates(db, reading)] == [900001, 900002, 900003]
    choice = {"card-1": {"instance_id": "short-name-copy", "card_id": 900002}}
    with pytest.raises(ValueError, match="Confirmer"):
        confirm_readings(db, ocr_report, choice)
    assert list_items(db) == []
    assert confirm_readings(db, ocr_report, choice, confirmed=True) == 1
    assert list_items(db)[0]["card_id"] == 900002


@pytest.mark.parametrize(
    "update",
    [
        {"name": "Exempl"},
        {"name": "Alex"},
        {"name": "@)"},
        {"rating": 90},
        {"position": "GK"},
        {"club_id": 9999},
    ],
)
def test_alias_never_relaxes_the_other_identity_checks(db, fixture, update):
    for card in fixture["catalogue"][:2]:
        card["aliases"] = ["Exemple"]
    save_cards(db, fixture["catalogue"])
    reading = CardReading.model_validate({**fixture["readings"][0], "name": "Exemple", **update})
    assert find_candidates(db, reading) == []


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
