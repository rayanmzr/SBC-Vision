"""Versions proches, doubles observations et protections, avec un club fictif."""

import json
import sqlite3
from copy import deepcopy
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
    sync_scan,
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


def test_visible_stats_distinguish_versions_and_are_rechecked_on_confirmation(
    db, fixture, ocr_report
):
    for card, pace in zip(fixture["catalogue"][:2], [70, 75], strict=True):
        card["stats"] = {"BasePace": pace}
    save_cards(db, fixture["catalogue"])
    raw = ocr_report["cards"][0]["reading"]
    raw["stats"] = {"PAC": 70}
    assert [c["id"] for c in find_candidates(db, CardReading.model_validate(raw))] == [900001]
    choice = {"card-1": {"instance_id": "stats-copy", "card_id": 900002}}
    with pytest.raises(ValueError, match="incompatible"):
        confirm_readings(db, ocr_report, choice, confirmed=True)
    assert list_items(db) == []
    choice["card-1"]["card_id"] = 900001
    assert confirm_readings(db, ocr_report, choice, confirmed=True) == 1


@pytest.mark.parametrize("stats", [None, {}, {"BasePace": 70.0}])
def test_missing_catalogue_stats_cannot_confirm_a_visible_stat(db, fixture, stats):
    for card in fixture["catalogue"]:
        card["stats"] = stats
    save_cards(db, fixture["catalogue"])
    reading = CardReading.model_validate({**fixture["readings"][0], "stats": {"PAC": 70}})
    assert find_candidates(db, reading) == []


@pytest.mark.parametrize("stats", [{"PAC": 100}, {"PAC": True}, {"PAC": "70"}, {"OVR": 70}])
def test_stats_contract_refuses_invalid_values_and_unknown_labels(fixture, stats):
    with pytest.raises(ValidationError):
        CardReading.model_validate({**fixture["readings"][0], "stats": stats})


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


def test_scan_preview_counts_overlap_and_real_copies_without_writing(db, fixture):
    captures = deepcopy(fixture["scan"])
    before = deepcopy(captures)
    result = sync_scan(db, captures)
    assert result == {
        "captures": 2,
        "observations": 4,
        "selected": 4,
        "items": 3,
        "reobserved": 1,
        "new": 3,
        "saved": 0,
        "pending": [],
    }
    assert list_items(db) == []
    assert captures == before


@pytest.mark.parametrize("preexisting", [False, True])
def test_scan_reuses_physical_ids_and_preserves_protection_score_and_tradeability(
    db, fixture, preexisting
):
    if preexisting:
        populate(db, fixture)
    captures = deepcopy(fixture["scan"])
    captures[0]["choices"]["card-1"]["protected"] = True
    captures[0]["report"]["cards"][1]["reading"]["item_score"] = 410
    captures[1]["choices"]["card-1"]["tradeable"] = None
    assert sync_scan(db, captures, confirmed=True)["saved"] == 3
    items = {item["instance_id"]: item for item in list_items(db)}
    assert len(items) == 3
    assert items["demo-001"]["card_id"] == items["demo-002"]["card_id"] == 900001
    assert items["demo-002"]["protected"] is True
    assert items["demo-002"]["tradeable"] is False
    assert items["demo-002"]["item_score"] == 410
    assert items["demo-002"]["source_observation"] == "demo-page-2:card-1"
    # Une nouvelle exécution ne duplique rien et ne retire pas les protections en base.
    captures[0]["choices"]["card-1"]["protected"] = False
    result = sync_scan(db, captures, confirmed=True)
    assert result["new"] == 0
    assert len(list_items(db)) == 3
    assert next(i for i in list_items(db) if i["instance_id"] == "demo-002")["protected"] is True


@pytest.mark.parametrize(
    "problem", ["version", "capture", "reading", "same-copy", "tradeable", "item_score"]
)
def test_bad_late_scan_observation_prevents_all_writes(db, fixture, problem):
    save_item(db, ClubItem.model_validate(fixture["items"][0]), confirmed=True)
    before = list_items(db)
    captures = deepcopy(fixture["scan"])
    second = captures[1]
    if problem == "version":
        second["choices"]["card-1"]["card_id"] = 900002
    elif problem == "capture":
        second["report"]["capture_id"] = captures[0]["report"]["capture_id"]
    elif problem == "reading":
        second["report"]["cards"][1]["reading"] = None
    elif problem == "same-copy":
        second["choices"]["card-2"]["instance_id"] = "demo-002"
    elif problem == "tradeable":
        second["choices"]["card-1"]["tradeable"] = True
    else:
        captures[0]["report"]["cards"][1]["reading"]["item_score"] = 410
        second["report"]["cards"][0]["reading"]["item_score"] = 420
    with pytest.raises(ValueError):
        sync_scan(db, captures, confirmed=True)
    assert list_items(db) == before


def test_partial_scan_keeps_unseen_items_and_reports_unselected_readings(db, fixture):
    populate(db, fixture)
    before = next(i for i in list_items(db) if i["instance_id"] == "demo-003")
    captures = deepcopy(fixture["scan"])
    del captures[1]["choices"]["card-2"]
    captures[1]["report"]["cards"][1]["reading"] = None
    captures[1]["report"]["cards"][1]["issues"] = ["Note illisible"]
    result = sync_scan(db, captures, confirmed=True)
    assert result["items"] == result["saved"] == 2
    assert result["pending"] == [{"capture_id": "demo-page-2", "element_id": "card-2"}]
    assert len(list_items(db)) == 3
    assert next(i for i in list_items(db) if i["instance_id"] == "demo-003") == before


def test_scan_with_no_confirmed_choices_does_not_invent_items(db, fixture):
    captures = deepcopy(fixture["scan"])
    for capture in captures:
        capture["choices"] = {}
    result = sync_scan(db, captures, confirmed=True)
    assert result["saved"] == result["items"] == result["selected"] == 0
    assert len(result["pending"]) == 4
    assert list_items(db) == []


def test_scan_preview_rejects_a_conflict_with_the_existing_inventory(db, fixture):
    item = {**fixture["items"][0], "card_id": 900002}
    save_item(db, ClubItem.model_validate(item), confirmed=True)
    before = list_items(db)
    with pytest.raises(ValueError, match="plusieurs versions"):
        sync_scan(db, deepcopy(fixture["scan"]))
    assert list_items(db) == before


def test_scan_cli_resolves_report_paths_and_requires_confirmation_for_writes(db, fixture, tmp_path):
    captures = deepcopy(fixture["scan"])
    for n, capture in enumerate(captures):
        path = tmp_path / f"page-{n}.json"
        path.write_text(json.dumps(capture["report"]))
        capture["report"] = path.name
    manifest, output = tmp_path / "scan.json", tmp_path / "summary.json"
    manifest.write_text(json.dumps(captures))
    database = db.execute("PRAGMA database_list").fetchone()[2]
    args = ["club", "--db", database, "scan", str(manifest), "--output", str(output)]
    assert main(args) == 0
    assert json.loads(output.read_text())["saved"] == 0
    assert list_items(db) == []
    assert main([*args, "--confirm"]) == 0
    assert json.loads(output.read_text())["saved"] == 3
    assert len(list_items(db)) == 3


def test_scan_demo_uses_simulated_tracking_and_can_be_repeated(tmp_path, capsys):
    database, output = tmp_path / "demo.sqlite3", tmp_path / "summary.json"
    args = ["club", "--db", str(database), "scan", "--demo", "--output", str(output)]
    assert main(args) == 0
    assert main(args) == 0
    assert json.loads(output.read_text())["new"] == 0
    assert "suivi des exemplaires simulés" in capsys.readouterr().out
    with open_database(database) as db:
        items = list_items(db)
        assert len(items) == 3 and sum(i["protected"] for i in items) == 1
    db.close()


def test_scan_demo_refuses_a_real_database_before_touching_its_output(db, fixture, tmp_path):
    save_cards(
        db, [{**fixture["catalogue"][0], "source_url": "https://www.futbin.com/27/player/1"}]
    )
    output = tmp_path / "summary.json"
    output.write_text('{"previous": true}')
    database = db.execute("PRAGMA database_list").fetchone()[2]
    assert main(["club", "--db", database, "scan", "--demo", "--output", str(output)]) == 1
    assert output.read_text() == '{"previous": true}'
    assert list_items(db) == []


@pytest.mark.parametrize("captures", [[], {}])
def test_empty_scan_cannot_erase_the_existing_inventory(db, fixture, captures):
    populate(db, fixture)
    before = list_items(db)
    with pytest.raises(ValueError):
        sync_scan(db, captures, confirmed=True)
    assert list_items(db) == before
