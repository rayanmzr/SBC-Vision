"""Raccord réel du lecteur de Rayan, plus limites du transport et erreurs HTTP."""

import json
import shutil
import time
from contextlib import closing
from dataclasses import replace
from hashlib import sha256
from io import BytesIO
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from PIL import Image, ImageDraw, ImageFont

from sbc_vision.api.main import app
from sbc_vision.api.ocr import get_ocr_limits, get_ocr_reader
from sbc_vision.api.sbc_workspace import SbcConfig, get_sbc_config
from sbc_vision.contracts.ocr import OcrAnalysisRequest, OcrAnalysisResponse
from sbc_vision.perception.ocr_regions import OcrBusyError, RegionOcrReader, load_ocr_reader


@pytest.fixture
def capture():
    image = Image.new("RGB", (800, 340), "white")
    draw, font = ImageDraw.Draw(image), ImageFont.load_default(size=36)
    labels = [("name", "ALEX EXEMPLE"), ("rating", "83"), ("position", "CM")]
    labels.append(("requirements", "Number of Players: 1"))
    regions = []
    for i, (field, text) in enumerate(labels):
        y = 10 + i * 80
        draw.text((30, y + 10), text, fill="black", font=font)
        regions.append(
            {
                "element_id": "rule-1" if field == "requirements" else "card-1",
                "field": field,
                "bbox": {"x": 10, "y": y, "width": 750, "height": 65},
            }
        )
    data = BytesIO()
    image.save(data, format="PNG")
    metadata = {
        "image": {"width": 800, "height": 340},
        "specification": {
            "capture_id": "synthetic-http-ocr",
            "regions": regions,
            "positions": ["CM"],
        },
    }
    return data.getvalue(), metadata


@pytest.fixture
def client(monkeypatch):
    monkeypatch.setenv("SBC_OCR_MODE", "disabled")
    app.dependency_overrides[get_sbc_config] = lambda: None
    with TestClient(app) as client:
        yield client
    app.dependency_overrides.clear()


def post(client, capture, *, metadata=None, image=None, media="image/png"):
    data, spec = capture
    return client.post(
        "/api/v1/ocr/analyze",
        files={"image": ("capture.png", data if image is None else image, media)},
        data={"metadata": json.dumps(spec if metadata is None else metadata)},
    )


class FailingReader:
    def __init__(self, error):
        self.error = error

    def analyze(self, *args):
        raise self.error


@pytest.fixture
def failing_reader(client):
    app.dependency_overrides[get_ocr_reader] = lambda: FailingReader(RuntimeError("private/path"))


def test_disabled_ocr_is_explicit_and_does_not_claim_a_detector(client, capture):
    assert post(client, capture).json()["detail"]["code"] == "ocr_unavailable"
    caps = client.get("/api/v1/capabilities").json()
    assert caps["ocr"] is False
    assert caps["ocr_mode"] == "disabled"
    assert caps["perception"] is False


@pytest.mark.parametrize("problem", ["json", "bounds", "duplicate", "count", "nan"])
def test_bad_regions_are_rejected_before_the_reader(client, capture, failing_reader, problem):
    metadata = capture[1]
    regions = metadata["specification"]["regions"]
    if problem == "json":
        metadata = "not an object"
    elif problem == "bounds":
        regions[0]["bbox"]["width"] = 900
    elif problem == "duplicate":
        regions.append(regions[0])
    elif problem == "count":
        metadata["specification"]["regions"] = [
            {**regions[0], "element_id": f"card-{i}"} for i in range(33)
        ]
    else:
        metadata["minimum_confidence"] = float("nan")
    response = post(client, capture, metadata=metadata)
    assert response.status_code == 422
    assert response.json()["detail"]["code"] == "invalid_ocr_regions"


@pytest.mark.parametrize(
    "image,media,status,code",
    [
        (b"broken", "image/png", 400, "invalid_image"),
        (b"broken", "image/jpeg", 400, "invalid_image"),
        (None, "image/jpeg", 415, "format_mismatch"),
        (None, "image/webp", 415, "unsupported_media_type"),
    ],
)
def test_bad_images_never_reach_ocr(client, capture, failing_reader, image, media, status, code):
    response = post(client, capture, image=image, media=media)
    assert response.status_code == status
    assert response.json()["detail"]["code"] == code


def test_dimensions_must_match_the_image(client, capture, failing_reader):
    capture[1]["image"]["height"] = 341
    response = post(client, capture)
    assert response.status_code == 422
    assert response.json()["detail"]["code"] == "ocr_image_mismatch"


def test_ocr_has_a_pixel_limit_before_expensive_enlargement(client, capture, failing_reader):
    app.dependency_overrides[get_ocr_limits] = lambda: replace(get_ocr_limits(), max_pixels=100)
    assert post(client, capture).status_code == 413


@pytest.mark.parametrize(
    "error,status,code",
    [(RuntimeError("private/path"), 502, "ocr_failed"), (OcrBusyError(), 429, "ocr_busy")],
)
def test_errors_are_distinct_without_exposing_details(client, capture, error, status, code):
    app.dependency_overrides[get_ocr_reader] = lambda: FailingReader(error)
    response = post(client, capture)
    assert response.status_code == status
    assert response.json()["detail"]["code"] == code
    assert "private/path" not in response.text


def test_reader_timeout_is_not_a_successful_empty_reading(client, capture):
    class SlowReader:
        def analyze(self, *args):
            time.sleep(0.1)

    app.dependency_overrides[get_ocr_reader] = lambda: SlowReader()
    app.dependency_overrides[get_ocr_limits] = lambda: replace(
        get_ocr_limits(), inference_timeout_seconds=0.01
    )
    response = post(client, capture)
    assert response.status_code == 504
    assert response.json()["detail"]["code"] == "ocr_timeout"


def test_invalid_mode_is_a_configuration_error(monkeypatch):
    monkeypatch.setenv("SBC_OCR_MODE", "made-up")
    with pytest.raises(RuntimeError, match="SBC_OCR_MODE"):
        load_ocr_reader()


@pytest.mark.skipif(shutil.which("tesseract") is None, reason="Tesseract requis")
def test_rayan_reader_runs_through_http_without_catalogue_or_account(client, capture):
    reader = RegionOcrReader()
    app.dependency_overrides[get_ocr_reader] = lambda: reader
    response = post(client, capture)
    assert response.status_code == 200, response.text
    report = OcrAnalysisResponse.model_validate_json(response.content)
    assert report.capture_id == "synthetic-http-ocr"
    assert report.region_source == "provided" and report.automatic_detection is False
    assert report.cards[0].reading.name == "ALEX EXEMPLE"
    assert report.cards[0].reading.rating == 83
    assert report.cards[0].reading.position == "CM"
    assert report.cards[0].needs_confirmation is True
    assert report.cards[0].candidate_ids == []
    assert report.challenge_ready is True
    assert report.challenge.positions == ["CM"]
    assert report.challenge.conditions[0].metric == "players"
    assert report.challenge.conditions[0].value == 1
    assert all(r.words and r.confidence > 0 for r in report.regions)
    caps = client.get("/api/v1/capabilities").json()
    assert caps["ocr"] is True and caps["ocr_regions_required"] is True
    assert caps["perception"] is False and caps["live_actions_enabled"] is False


@pytest.mark.skipif(shutil.which("tesseract") is None, reason="Tesseract requis")
def test_busy_worker_is_refused_even_if_the_previous_http_request_ended(capture):
    reader = RegionOcrReader()
    reader.slot.acquire()
    try:
        with pytest.raises(OcrBusyError):
            reader.analyze(capture[0], OcrAnalysisRequest.model_validate(capture[1]))
    finally:
        reader.slot.release()


@pytest.mark.skipif(shutil.which("tesseract") is None, reason="Tesseract requis")
def test_catalogue_matching_is_read_only_and_does_not_confirm_an_owned_card(
    client, capture, tmp_path
):
    from sbc_vision.sbc_engine.players import open_database, save_cards

    database = tmp_path / "catalogue.sqlite3"
    catalogue = json.loads(
        (Path(__file__).resolve().parents[1] / "data/fixtures/club.synthetic.json").read_text()
    )["catalogue"]
    with closing(open_database(database)) as db:
        save_cards(db, catalogue)
    before = sha256(database.read_bytes()).hexdigest()
    reader = RegionOcrReader()
    app.dependency_overrides[get_ocr_reader] = lambda: reader
    app.dependency_overrides[get_sbc_config] = lambda: SbcConfig(database, None, "demo")
    response = post(client, capture)
    assert response.status_code == 200, response.text
    assert response.json()["cards"][0]["candidate_ids"] == [900001, 900002]
    assert response.json()["cards"][0]["needs_confirmation"] is True
    assert sha256(database.read_bytes()).hexdigest() == before


@pytest.mark.skipif(shutil.which("tesseract") is None, reason="Tesseract requis")
def test_malformed_confident_rating_is_preserved_but_not_normalized(client, capture, monkeypatch):
    reader = RegionOcrReader()
    regions = [
        {
            **r,
            "text": "ALEX EXEMPLE" if r["field"] == "name" else "8B",
            "confidence": 0.99,
            "words": [],
            "method": "global",
        }
        for r in capture[1]["specification"]["regions"][:2]
    ]
    monkeypatch.setattr(reader.ocr, "read_regions", lambda *a, **kw: regions)
    app.dependency_overrides[get_ocr_reader] = lambda: reader
    response = post(client, capture)
    assert response.status_code == 200
    report = response.json()
    assert report["regions"][1]["text"] == "8B"
    assert report["cards"][0]["reading"] is None
    assert report["cards"][0]["candidate_ids"] == []
    assert report["cards"][0]["issues"]
