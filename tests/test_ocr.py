"""Lectures locales sur images fictives et traitement des incertitudes."""

import json
import shutil
from contextlib import closing
from datetime import UTC, datetime
from pathlib import Path

import pytest
from PIL import Image, ImageDraw, ImageFont
from pydantic import ValidationError

from sbc_vision.sbc_engine.models import OcrInput
from sbc_vision.sbc_engine.ocr import (
    analyze,
    challenge_from_ocr,
    edit_distance,
    evaluate,
    read_regions,
)
from sbc_vision.sbc_engine.players import (
    confirm_readings,
    list_items,
    open_database,
    save_cards,
    seed_demo,
)


def specification():
    return OcrInput.model_validate(
        {
            "capture_id": "synthetic-screen",
            "regions": [
                {
                    "element_id": "card-1",
                    "field": field,
                    "bbox": {"x": 10, "y": y, "width": 750, "height": 65},
                }
                for field, y in [("name", 10), ("rating", 80), ("position", 145)]
            ],
        }
    )


@pytest.fixture
def db(tmp_path):
    path = Path(__file__).resolve().parents[1] / "data/fixtures/club.synthetic.json"
    fixture = json.loads(path.read_text())
    with closing(open_database(tmp_path / "ocr.sqlite3")) as db:
        save_cards(db, fixture["catalogue"])
        yield db


@pytest.mark.skipif(shutil.which("tesseract") is None, reason="Tesseract doit être installé")
def test_real_ocr_requires_a_chosen_version_before_adding_an_owned_item(tmp_path, db):
    image = Image.new("RGB", (800, 230), "white")
    draw, font = ImageDraw.Draw(image), ImageFont.load_default(size=36)
    for text, y in [("ALEX EXEMPLE", 25), ("83", 95), ("CM", 160)]:
        draw.text((30, y), text, fill="black", font=font)
    path = tmp_path / "synthetic.png"
    image.save(path)
    report = analyze(path, specification(), db)
    assert report["cards"][0]["reading"]["rating"] == 83
    assert report["cards"][0]["candidate_ids"] == [900001, 900002]
    assert report["cards"][0]["needs_confirmation"] is True
    assert list_items(db) == []
    for region in report["regions"]:
        for word in region["words"]:
            assert 0 <= word["x"] < image.width
            assert 0 <= word["y"] < image.height
    confirm_readings(
        db, report, {"card-1": {"instance_id": "ocr-copy", "card_id": 900001}}, confirmed=True
    )
    assert list_items(db)[0]["card_id"] == 900001
    assert list_items(db)[0]["source_observation"] == "synthetic-screen:card-1"


@pytest.mark.parametrize("rating, confidence", [("8B", 0.99), ("83", 0.2), ("", 0)])
def test_unreadable_rating_never_becomes_a_confirmed_card(monkeypatch, db, rating, confidence):
    monkeypatch.setattr(
        "sbc_vision.sbc_engine.ocr.read_regions",
        lambda *a, **kw: [
            {"element_id": "card-1", "field": "name", "text": "Alex Exemple", "confidence": 0.99},
            {"element_id": "card-1", "field": "rating", "text": rating, "confidence": confidence},
        ],
    )
    report = analyze("unused.png", specification(), db)
    assert report["cards"][0]["reading"] is None
    assert report["cards"][0]["issues"]
    assert list_items(db) == []


def test_out_of_bounds_region_is_rejected_before_ocr(tmp_path):
    path = tmp_path / "tiny.png"
    Image.new("RGB", (10, 10), "white").save(path)
    with pytest.raises(ValueError, match="hors de l'image"):
        read_regions(path, specification())


def test_duplicate_fields_cannot_silently_overwrite_one_another():
    data = specification().model_dump()
    data["regions"].append(data["regions"][0])
    with pytest.raises(ValidationError, match="Une seule région"):
        OcrInput.model_validate(data)


@pytest.mark.skipif(shutil.which("tesseract") is None, reason="Tesseract doit être installé")
def test_real_capture_conditions_become_a_dynamic_request(tmp_path, db):
    image = Image.new("RGB", (1000, 300), "white")
    draw, font = ImageDraw.Draw(image), ImageFont.load_default(size=36)
    for text, y in [
        ("Number of players: 3", 20),
        ("Player rating: Min 82", 90),
        ("Rare players: Min 1", 160),
    ]:
        draw.text((30, y), text, fill="black", font=font)
    path = tmp_path / "conditions.png"
    image.save(path)
    spec = OcrInput(
        capture_id="new-sbc",
        positions=["CAM", "CM", "ST"],
        regions=[
            {
                "element_id": "requirements",
                "field": "requirements",
                "bbox": {"x": 0, "y": 0, "width": 1000, "height": 300},
            }
        ],
    )
    report = analyze(path, spec, db)
    parsed = challenge_from_ocr(report, db, market="pc", budget=2000)
    assert parsed["ready"], parsed["issues"]
    assert parsed["challenge"]["positions"] == ["CAM", "CM", "ST"]
    assert [c["metric"] for c in parsed["challenge"]["conditions"]] == ["players", "rating", "rare"]

    # Le même rapport OCR est ensuite consommé par la commande du solveur.
    from sbc_vision.sbc_engine.__main__ import main

    root = Path(__file__).resolve().parents[1]
    club = json.loads((root / "data/fixtures/club.synthetic.json").read_text())
    demo = json.loads((root / "data/fixtures/solver.synthetic.json").read_text())
    seed_demo(db, club, demo["extra_cards"])
    cards = [json.loads(row["data"]) for row in db.execute("SELECT data FROM cards")]
    for card in cards:
        card["observed_at"] = datetime.now(UTC).isoformat()
    save_cards(db, cards)
    db_path = db.execute("PRAGMA database_list").fetchone()[2]
    regions, reading, output = [
        tmp_path / name for name in ["regions.json", "reading.json", "plan.json"]
    ]
    regions.write_text(spec.model_dump_json())
    assert (
        main(
            [
                "ocr",
                str(path),
                str(regions),
                "--db",
                db_path,
                "--market",
                "pc",
                "--budget",
                "2000",
                "--output",
                str(reading),
            ]
        )
        == 0
    )
    assert main(["solve", "--reading", str(reading), "--db", db_path, "--output", str(output)]) == 0
    assert json.loads(output.read_text())["solution"]["total_cost"] == 2100


def text_report(text, *, capture="screen-1", field="name", confidence=0.99):
    return {
        "capture_id": capture,
        "regions": [
            {"element_id": "card-1", "field": field, "text": text, "confidence": confidence}
        ],
    }


@pytest.mark.parametrize(
    "expected, actual, edits",
    [("kitten", "sitting", 3), ("ABC", "AB", 1), ("AB", "AXB", 1), ("É", "E", 1), ("", "AB", 2)],
)
def test_character_distance_counts_insertions_deletions_and_substitutions(expected, actual, edits):
    assert edit_distance(expected, actual) == edits


def test_batch_cer_is_weighted_by_characters_and_separates_fields():
    expected = [text_report("ABCDEFGHIJ"), text_report("8", capture="screen-2", field="rating")]
    observed = [text_report("ABCDEFGHIK"), text_report("9", capture="screen-2", field="rating")]
    metrics = evaluate(observed, expected)
    assert metrics["summary"]["fields"] == 2
    assert metrics["summary"]["characters"] == 11
    assert metrics["summary"]["cer"] == pytest.approx(2 / 11)
    assert metrics["by_field"]["name"]["cer"] == pytest.approx(0.1)
    assert metrics["by_field"]["rating"]["cer"] == 1
    assert metrics["summary"]["exact_accuracy"] == 0


def test_missing_or_uncertain_fields_are_never_reported_as_accepted_correct_fields():
    expected = [text_report("ABC"), text_report("83", capture="screen-2", field="rating")]
    observed = [text_report("ABC", confidence=0.2), text_report("extra", capture="another-screen")]
    metrics = evaluate(observed, expected)
    assert metrics["missing_regions"] == 1
    assert metrics["unexpected_regions"] == 1
    assert metrics["summary"]["cer"] == pytest.approx(2 / 5)
    assert metrics["summary"]["exact_accuracy"] == 0
    assert metrics["summary"]["unknown_rate"] == 1


def test_unicode_and_whitespace_are_normalized_without_hiding_real_errors():
    metrics = evaluate(text_report("E\u0301li\n  Test"), text_report("Éli Test"))
    assert metrics["summary"]["cer"] == 0
    assert metrics["summary"]["exact_accuracy"] == 1
    assert evaluate(text_report("a"), text_report("A"))["summary"]["cer"] == 1
    assert evaluate(text_report("ABC"), text_report("A"))["summary"]["cer"] == 2


@pytest.mark.parametrize("problem", ["duplicate", "empty", "confidence", "blank", "threshold"])
def test_invalid_evaluation_input_does_not_produce_plausible_metrics(problem):
    observed, expected, minimum = text_report("Alex"), text_report("Alex"), 0.75
    if problem == "duplicate":
        expected["regions"].append(expected["regions"][0])
    elif problem == "empty":
        expected = []
    elif problem == "confidence":
        observed["regions"][0]["confidence"] = -0.1
    elif problem == "blank":
        expected["regions"][0]["text"] = " "
    else:
        minimum = 1.1
    with pytest.raises(ValueError):
        evaluate(observed, expected, minimum=minimum)


@pytest.mark.skipif(shutil.which("tesseract") is None, reason="Tesseract doit être installé")
def test_evaluation_cli_creates_a_reproducible_synthetic_demo(tmp_path):
    from sbc_vision.sbc_engine.__main__ import main

    output, replay = tmp_path / "metrics.json", tmp_path / "replay.json"
    assert main(["evaluate", "--demo", "--output", str(output)]) == 0
    metrics = json.loads(output.read_text())
    assert metrics["data_kind"] == "synthetic"
    assert metrics["summary"]["fields"] == 6
    assert metrics["summary"]["characters"] > 0
    assert metrics["summary"]["cer"] >= 0
    assert (tmp_path / "ocr_demo.png").is_file()
    assert (
        main(
            [
                "evaluate",
                "--reading",
                str(tmp_path / "ocr_demo.report.json"),
                "--expected",
                str(tmp_path / "ocr_demo.expected.json"),
                "--output",
                str(replay),
            ]
        )
        == 0
    )
    assert json.loads(replay.read_text())["summary"] == metrics["summary"]
    assert main(["evaluate", "--reading", str(tmp_path / "ocr_demo.report.json")]) == 1
