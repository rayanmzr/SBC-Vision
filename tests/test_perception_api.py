"""Tests de transport avec un pipeline fictif explicite, sans mesure de vision."""

import asyncio
import json
from copy import deepcopy
from dataclasses import replace
from io import BytesIO
from pathlib import Path

import httpx
import pytest
from fastapi.testclient import TestClient
from PIL import Image

from sbc_vision.api.main import app
from sbc_vision.api.perception import (
    AnalysisLimits,
    get_analysis_limits,
    get_perception_pipeline,
)
from sbc_vision.contracts.perception import PerceptionResponse

FIXTURES = Path(__file__).resolve().parents[1] / "data/fixtures"


class FixturePipeline:
    def __init__(self):
        self.payload = json.loads((FIXTURES / "perception.synthetic.json").read_text())
        self.calls = []

    async def analyze(self, capture):
        self.calls.append((capture.capture_id, capture.image.size, capture.image.mode))
        result = deepcopy(self.payload)
        result["capture_id"] = capture.capture_id
        return result


@pytest.fixture
def pipeline():
    return FixturePipeline()


@pytest.fixture
def client(pipeline):
    app.dependency_overrides[get_perception_pipeline] = lambda: pipeline
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()


@pytest.fixture
def png():
    return (FIXTURES / "perception.synthetic.png").read_bytes()


def post(client, data, media="image/png", capture_id="transport-test"):
    return client.post(
        "/api/v1/perception/analyze",
        params={"capture_id": capture_id},
        content=data,
        headers={"Content-Type": media},
    )


def test_capture_reaches_pipeline_and_response_matches_contract(client, pipeline, png):
    response = post(client, png)
    assert response.status_code == 200
    result = PerceptionResponse.model_validate(response.json())
    assert result.model_name == "synthetic-fixture-no-inference"
    assert result.capture_id == "transport-test"
    assert result.elements[0].bbox.x == 40
    assert pipeline.calls == [("transport-test", (1280, 720), "RGB")]


def test_jpeg_is_supported(client, pipeline):
    stream = BytesIO()
    Image.new("RGB", (1280, 720)).save(stream, format="JPEG")
    assert post(client, stream.getvalue(), "image/jpeg").status_code == 200
    assert len(pipeline.calls) == 1


def test_server_can_generate_capture_identifier(client, png):
    response = client.post(
        "/api/v1/perception/analyze", content=png, headers={"Content-Type": "image/png"}
    )
    assert response.status_code == 200
    assert response.json()["capture_id"]


def test_no_detection_is_a_successful_result(client, pipeline, png):
    pipeline.payload["elements"] = []
    response = post(client, png)
    assert response.status_code == 200
    assert response.json()["elements"] == []


def test_missing_pipeline_returns_unavailable_instead_of_fake_elements(client, png):
    app.dependency_overrides[get_perception_pipeline] = lambda: None
    response = post(client, png)
    assert response.status_code == 503
    assert response.json()["detail"]["code"] == "perception_unavailable"
    assert "elements" not in response.json()


@pytest.mark.parametrize("media", ["text/plain", "image/svg+xml", "application/json", ""])
def test_unsupported_content_type_never_reaches_pipeline(client, pipeline, png, media):
    response = post(client, png, media)
    assert response.status_code == 415
    assert pipeline.calls == []


@pytest.mark.parametrize("data", [b"", b"not an image", b"\x89PNG\r\n\x1a\n"])
def test_invalid_image_never_reaches_pipeline(client, pipeline, data):
    assert post(client, data).status_code == 400
    assert pipeline.calls == []


def test_declared_format_must_match_file(client, pipeline, png):
    response = post(client, png, "image/jpeg")
    assert response.status_code == 415
    assert response.json()["detail"]["code"] == "format_mismatch"
    assert pipeline.calls == []


def test_actual_payload_size_is_limited_even_with_wrong_content_length(client, pipeline, png):
    app.dependency_overrides[get_analysis_limits] = lambda: replace(AnalysisLimits(), max_bytes=32)
    response = client.post(
        "/api/v1/perception/analyze",
        content=png,
        headers={"Content-Type": "image/png", "Content-Length": "1"},
    )
    assert response.status_code == 413
    assert pipeline.calls == []


@pytest.mark.parametrize("override", [{"max_dimension": 1000}, {"max_pixels": 1000}])
def test_dimensions_are_checked_before_inference(client, pipeline, png, override):
    app.dependency_overrides[get_analysis_limits] = lambda: replace(AnalysisLimits(), **override)
    response = post(client, png)
    assert response.status_code == 413
    assert response.json()["detail"]["code"] == "image_too_large"
    assert pipeline.calls == []


@pytest.mark.parametrize("identifier", ["", "x" * 129])
def test_invalid_capture_identifier_is_rejected(client, pipeline, png, identifier):
    assert post(client, png, capture_id=identifier).status_code == 422
    assert pipeline.calls == []


@pytest.mark.parametrize("case", ["wrong_capture", "wrong_dimensions", "outside_box"])
def test_inconsistent_pipeline_result_is_not_sent_to_controller(client, pipeline, png, case):
    if case == "wrong_capture":

        async def wrong_capture(capture):
            return pipeline.payload

        pipeline.analyze = wrong_capture
    elif case == "wrong_dimensions":
        pipeline.payload["image"]["width"] = 1281
    else:
        pipeline.payload["elements"][0]["bbox"]["x"] = 1280
    response = post(client, png)
    assert response.status_code == 502
    assert response.json()["detail"]["code"] == "invalid_perception_result"


def test_pipeline_error_does_not_expose_internal_details(client, pipeline, png):
    async def fail(capture):
        raise RuntimeError("private/path/or/credentials")

    pipeline.analyze = fail
    response = post(client, png)
    assert response.status_code == 502
    assert "private/path" not in response.text
    assert response.json()["detail"]["code"] == "inference_failed"


def test_inference_deadline_returns_timeout(client, pipeline, png):
    async def slow(capture):
        await asyncio.sleep(10)

    pipeline.analyze = slow
    app.dependency_overrides[get_analysis_limits] = lambda: replace(
        AnalysisLimits(), inference_timeout_seconds=0.01
    )
    response = post(client, png)
    assert response.status_code == 504
    assert response.json()["detail"]["code"] == "inference_timeout"


def test_upload_deadline_returns_timeout(client, pipeline):
    app.dependency_overrides[get_analysis_limits] = lambda: replace(
        AnalysisLimits(), upload_timeout_seconds=0.01
    )

    async def send_slow_upload():
        async def chunks():
            yield b"first chunk"
            await asyncio.sleep(10)

        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url="http://test"
        ) as async_client:
            return await async_client.post(
                "/api/v1/perception/analyze",
                content=chunks(),
                headers={"Content-Type": "image/png"},
            )

    response = asyncio.run(send_slow_upload())
    assert response.status_code == 408
    assert pipeline.calls == []


def test_openapi_documents_binary_input_success_and_errors(client):
    operation = client.get("/openapi.json").json()["paths"]["/api/v1/perception/analyze"]["post"]
    assert set(operation["requestBody"]["content"]) == {"image/png", "image/jpeg"}
    assert {"200", "400", "408", "413", "415", "422", "502", "503", "504"} <= set(
        operation["responses"]
    )
