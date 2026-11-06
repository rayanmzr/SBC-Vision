"""Lectures locales sur images fictives et traitement des incertitudes."""

import json
import shutil
from contextlib import closing
from pathlib import Path

import pytest
from PIL import Image, ImageDraw, ImageFont
from pydantic import ValidationError

from sbc_vision.sbc_engine.catalogue import open_database, save_cards
from sbc_vision.sbc_engine.inventory import list_items
from sbc_vision.sbc_engine.models import OcrInput
from sbc_vision.sbc_engine.ocr import analyze, read_regions


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
