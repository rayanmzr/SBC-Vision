"""Vraie route HTTP et vraie lecture des pixels du laboratoire, sans modèle EA."""

import asyncio
from io import BytesIO

import pytest
from fastapi.testclient import TestClient
from PIL import Image, ImageDraw

from sbc_vision.api.main import app
from sbc_vision.perception.lab_colors import MARKERS, LabColorPipeline
from sbc_vision.perception.pipeline import Capture, UnrecognizedSceneError


def scene(stage=0, *, offset=(35, 55), scale=1):
    image = Image.new("RGB", (640 * scale, 270 * scale), "white")
    x, y = offset
    ImageDraw.Draw(image).rectangle(
        (x * scale, y * scale, (x + 80) * scale - 1, (y + 40) * scale - 1),
        fill=MARKERS[stage][2],
    )
    return image


def post(client, image, identifier="lab-capture"):
    body = BytesIO()
    image.save(body, format="PNG")
    return client.post(
        "/api/v1/perception/analyze",
        params={"capture_id": identifier},
        content=body.getvalue(),
        headers={"Content-Type": "image/png"},
    )


@pytest.mark.parametrize("stage", [0, 1, 2])
@pytest.mark.parametrize("scale", [1, 2])
def test_real_pixels_determine_state_and_original_box(stage, scale):
    result = asyncio.run(LabColorPipeline().analyze(Capture("capture", scene(stage, scale=scale))))
    assert result.capture_id == "capture"
    assert result.model_name == "lab-color-api-v1"
    assert result.elements[0].id == MARKERS[stage][0]
    assert result.elements[0].bbox.model_dump() == {
        "x": 35 * scale,
        "y": 55 * scale,
        "width": 80 * scale,
        "height": 40 * scale,
    }
    assert result.elements[0].actions == ([] if stage == 2 else ["click"])


@pytest.mark.parametrize("fault", ["none", "multiple", "masked", "duplicated", "small"])
def test_unknown_or_ambiguous_scene_never_yields_an_action(fault):
    image = scene()
    draw = ImageDraw.Draw(image)
    if fault == "none":
        draw.rectangle((0, 0, 639, 269), fill="white")
    elif fault == "multiple":
        draw.rectangle((200, 50, 280, 90), fill=MARKERS[1][2])
    elif fault == "masked":
        draw.rectangle((60, 65, 80, 80), fill="white")
    elif fault == "duplicated":
        draw.rectangle((200, 50, 280, 90), fill=MARKERS[0][2])
    else:
        image = Image.new("RGB", (12, 12), MARKERS[0][2])
    with pytest.raises(UnrecognizedSceneError):
        asyncio.run(LabColorPipeline().analyze(Capture("capture", image)))


def test_explicit_mode_uses_real_route_and_never_claims_trained_model(monkeypatch):
    monkeypatch.setenv("SBC_PERCEPTION_MODE", "lab-colors")
    with TestClient(app) as client:
        caps = client.get("/api/v1/capabilities").json()
        assert caps["perception"] is True
        assert caps["perception_mode"] == "lab-colors"
        assert caps["ocr"] is False
        assert caps["live_actions_enabled"] is False
        assert client.get("/health").json()["model_loaded"] is False
        for stage in range(3):
            response = post(client, scene(stage), identifier=f"fresh-{stage}")
            assert response.status_code == 200
            assert response.json()["capture_id"] == f"fresh-{stage}"
            assert response.json()["elements"][0]["id"] == MARKERS[stage][0]
        response = post(client, Image.new("RGB", (100, 100), "white"))
        assert response.status_code == 422
        assert response.json()["detail"]["code"] == "scene_unrecognized"
        assert "elements" not in response.json()


def test_disabled_default_is_restored_after_lab_shutdown(monkeypatch):
    monkeypatch.setenv("SBC_PERCEPTION_MODE", "lab-colors")
    with TestClient(app) as client:
        assert post(client, scene()).status_code == 200
    monkeypatch.delenv("SBC_PERCEPTION_MODE")
    with TestClient(app) as client:
        assert post(client, scene()).status_code == 503
        caps = client.get("/api/v1/capabilities").json()
        assert caps["perception"] is False
        assert caps["perception_mode"] == "disabled"


def test_unknown_mode_fails_startup_instead_of_enabling_demo(monkeypatch):
    monkeypatch.setenv("SBC_PERCEPTION_MODE", "typo")
    with pytest.raises(RuntimeError, match="SBC_PERCEPTION_MODE"):
        with TestClient(app):
            pass
