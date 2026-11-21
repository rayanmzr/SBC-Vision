"""Images fictives : parcours vision, preuves locales et inventaire séparé."""

import hashlib
import json
import shutil
from contextlib import closing
from io import BytesIO
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock

import pytest
from fastapi.testclient import TestClient
from PIL import Image, ImageDraw, ImageFont

from sbc_vision.api.main import app
from sbc_vision.api.perception import get_perception_pipeline
from sbc_vision.api.sbc_workspace import SbcConfig, SbcWorkspace, get_workspace
from sbc_vision.contracts.ocr import VisionFrame
from sbc_vision.perception.pipeline import Capture, DetectorPipeline
from sbc_vision.sbc_engine.players import open_database, seed_demo


def synthetic_image():
    image = Image.new("RGB", (1512, 860), "#171e29")
    draw = ImageDraw.Draw(image)

    def text(x, y, value, size=20, fill="white"):
        draw.text((x, y), value, fill=fill, font=ImageFont.load_default(size=size))

    text(112, 60, "My Club Players", 30)
    text(25, 520, "Club")
    text(225, 790, "Previous")
    text(880, 790, "Next")
    for top, name, rating in [(335, "ALEX EXEMPLE", "83"), (515, "SAM DEMO", "75")]:
        draw.rectangle((238, top - 46, 308, top + 55), fill="#eadb90", outline="white", width=2)
        text(244, top - 33, rating, 16, "black")
        text(239, top - 19, "CM", 11, "black")
        text(320, top - 45, name, 25)
        for i, label in enumerate(["PAC", "SHO", "PAS", "DRI", "DEF", "PHY"]):
            text(320 + 27 * i, top, label, 12)
            text(320 + 27 * i, top + 18, str(70 + i), 18)
    return image


@pytest.fixture
def service(tmp_path):
    database = tmp_path / "synthetic.sqlite3"
    fixtures = Path(__file__).resolve().parents[1] / "data/fixtures"
    with closing(open_database(database)) as db:
        seed_demo(db, json.loads((fixtures / "club.synthetic.json").read_text()), [])
        for row in db.execute("SELECT id,data FROM cards").fetchall():
            card = json.loads(row["data"])
            card["source_url"] = f"https://example.test/synthetic/{row['id']}"
            db.execute("UPDATE cards SET data=? WHERE id=?", (json.dumps(card), row["id"]))
        db.commit()
    return SbcWorkspace(SbcConfig(database, None, "local"))


@pytest.mark.skipif(shutil.which("tesseract") is None, reason="Tesseract doit être installé")
def test_pixel_route_detects_reads_and_persists_without_html(monkeypatch, service):
    from sbc_vision.perception.ocr_regions import RegionOcrReader

    class Detector:
        name = "synthetic-empty-detector"

        def detect(self, image):
            assert image.shape == (860, 1512, 3)
            return []  # Le complément OpenCV/OCR doit rester explicite.

    monkeypatch.setattr("sbc_vision.perception.detector.load_detector", lambda _: Detector())
    pipeline = DetectorPipeline(
        "synthetic", reader=RegionOcrReader(), database=service.config.database
    )
    app.dependency_overrides[get_perception_pipeline] = lambda: pipeline
    before = service.snapshot().items
    data = BytesIO()
    synthetic_image().save(data, "PNG")
    try:
        with TestClient(app) as client:
            assert (
                client.post(
                    "/api/v1/perception/club-analyze", json={"html": "My Club Players"}
                ).status_code
                == 415
            )
            result = client.post(
                "/api/v1/perception/club-analyze?capture_id=synthetic-pixels",
                content=data.getvalue(),
                headers={"Content-Type": "image/png"},
            )
        assert result.status_code == 200, result.text
        frame = VisionFrame.model_validate(result.json())
        assert frame.scene == "players"
        assert set(frame.controls) == {"club", "previous", "next"}
        assert len(frame.rows) == 2
        assert all(row.detector == "opencv-ocr" for row in frame.rows)
        assert [(c.reading.name, c.reading.rating) for c in frame.ocr.cards] == [
            ("ALEX EXEMPLE", 83),
            ("SAM DEMO", 75),
        ]
        # Une statistique lue sous le seuil ne devient jamais un rapprochement confirmé.
        for card in frame.ocr.cards:
            if card.issues:
                assert card.issues == ["Statistiques à relire."]
                assert not card.candidate_ids
        assert frame.image_sha256 == hashlib.sha256(data.getvalue()).hexdigest()
        assert service.snapshot().items == before
        proof = service.config.database.parent / "vision_proof"
        assert len(list(proof.glob("*.png"))) == 1
    finally:
        app.dependency_overrides.clear()


def save_frame(service, identifier, *, next_page=False):
    data = BytesIO()
    Image.new("RGB", (100, 80), "white").save(data, "PNG")
    frame = VisionFrame(
        capture_id=identifier,
        image={"width": 100, "height": 80},
        model_name="synthetic",
        image_sha256=hashlib.sha256(data.getvalue()).hexdigest(),
        screen_hash="a" * 64,
        scene="players",
        list_bbox={"x": 10, "y": 10, "width": 70, "height": 50},
        controls={"next": {"x": 60, "y": 70, "width": 20, "height": 5}} if next_page else {},
        rows=[],
        ocr={
            "capture_id": identifier,
            "image": {"width": 100, "height": 80},
            "engine_version": "synthetic",
            "language": "eng",
            "minimum_confidence": 0.75,
            "regions": [],
            "positions": [],
            "challenge_ready": False,
            "challenge": None,
            "challenge_issues": [],
            "cards": [
                {
                    "element_id": "row-1",
                    "candidate_ids": [900001],
                    "issues": [],
                    "needs_confirmation": True,
                    "reading": {
                        "capture_id": identifier,
                        "element_id": "row-1",
                        "name": "Alex Exemple",
                        "rating": 83,
                        "confidence": 0.95,
                    },
                }
            ],
        },
    )
    directory = service.config.database.parent / "vision_proof"
    directory.mkdir(exist_ok=True)
    key = hashlib.sha256(identifier.encode()).hexdigest()
    (directory / f"{key}.png").write_bytes(data.getvalue())
    (directory / f"{key}.json").write_text(frame.model_dump_json())
    return directory / f"{key}.png"


@pytest.mark.parametrize(
    "fault", [None, "missing", "changed", "duplicate", "action", "end", "html"]
)
def test_scan_proof_is_checked_and_never_replaces_owned_copies(service, fault):
    before = service.snapshot().items
    path = save_frame(service, "synthetic-1")
    save_frame(service, "synthetic-2", next_page=fault == "end")
    body = {
        "capture_ids": ["synthetic-1", "synthetic-2"],
        "complete": True,
        "actions": [{"capture_id": "synthetic-1", "action": "down"}],
    }
    if fault == "missing":
        path.unlink()
    if fault == "changed":
        path.write_bytes(b"changed")
    if fault == "duplicate":
        body["capture_ids"] = ["synthetic-1"] * 2
    if fault == "action":
        body["actions"][0]["action"] = "next"
    if fault == "html":
        body["cards"] = [{"name": "HTML injection"}]
    app.dependency_overrides[get_workspace] = lambda: service
    try:
        with TestClient(app) as client:
            result = client.post("/api/v1/sbc/vision-scan", json=body)
        assert result.status_code == (422 if fault else 200), result.text
        if not fault:
            report = result.json()
            assert report["source"] == "vision"
            assert report["readings"] == report["identified"] == 1  # Dédupliquer le chevauchement.
            assert report["inventory_updated"] is False
            with closing(open_database(service.config.database)) as db:
                assert (
                    json.loads(db.execute("SELECT data FROM vision_scans").fetchone()[0]) == report
                )
        assert service.snapshot().items == before
    finally:
        app.dependency_overrides.clear()


def test_vision_refuses_html_payload_or_missing_model():
    app.dependency_overrides[get_perception_pipeline] = lambda: None
    try:
        with TestClient(app) as client:
            response = client.post("/api/v1/perception/club-analyze", json={"html": "Players"})
        assert response.status_code == 503
        assert response.json()["detail"]["code"] == "vision_unavailable"
    finally:
        app.dependency_overrides.clear()


@pytest.mark.parametrize("heading,expected", [("SBC", "other"), ("Club", "club")])
def test_club_navigation_does_not_confuse_sidebar_or_sbc_players_tab(
    monkeypatch, heading, expected
):
    from sbc_vision.perception.club_vision import observe_club

    def word(text, x, y, line):
        return {
            "text": text,
            "x": x,
            "y": y,
            "width": 80,
            "height": 22,
            "confidence": 0.96,
            "line": (line, 1, 1),
        }

    global_words = [
        word(heading, 112, 60, 1),
        word("Club", 25, 520, 2),
        word("Players", 480, 150, 3),
    ]
    reader = Mock(side_effect=[global_words, [word("Players", 380, 190, 4)]])
    monkeypatch.setattr("sbc_vision.perception.club_vision.ocr_words", reader)
    frame = observe_club(
        Capture("synthetic-menu", Image.new("RGB", (1512, 860), "black")),
        SimpleNamespace(name="synthetic-detector"),
        SimpleNamespace(language="eng"),
        None,
    )
    assert frame.scene == expected
    assert set(frame.controls) == ({"club", "players"} if heading == "Club" else {"club"})
    assert reader.call_count == (2 if heading == "Club" else 1)
