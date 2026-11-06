"""Lectures locales sur images fictives et traitement des incertitudes."""

import json
import shutil
from contextlib import closing
from datetime import UTC, datetime
from pathlib import Path

import pytest
from PIL import Image, ImageDraw, ImageFont
from pydantic import ValidationError

from sbc_vision.sbc_engine.catalogue import open_database, save_cards
from sbc_vision.sbc_engine.inventory import list_items, seed_demo
from sbc_vision.sbc_engine.models import OcrInput
from sbc_vision.sbc_engine.ocr import analyze, challenge_from_ocr, read_regions


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
def test_real_ocr_proposes_versions_without_creating_owned_items(tmp_path, db):
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
