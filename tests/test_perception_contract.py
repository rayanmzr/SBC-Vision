import json
from copy import deepcopy
from pathlib import Path

import pytest
from pydantic import ValidationError

from sbc_vision.contracts.perception import PerceptionResponse

FIXTURE = Path(__file__).resolve().parents[1] / "data/fixtures/perception.synthetic.json"


@pytest.fixture
def payload():
    return json.loads(FIXTURE.read_text())


def test_offline_fixture_uses_capture_coordinates(payload):
    result = PerceptionResponse.model_validate(payload)
    assert result.image.width == 1280
    assert result.elements[0].bbox.x == 40


@pytest.mark.parametrize(
    "bbox",
    [
        {"x": -1, "y": 0, "width": 1, "height": 1},
        {"x": 1270, "y": 0, "width": 20, "height": 1},
        {"x": 0, "y": 719, "width": 1, "height": 2},
        {"x": 0, "y": 0, "width": 0, "height": 1},
        {"x": 0.5, "y": 0, "width": 1, "height": 1},
    ],
)
def test_unusable_action_coordinates_are_rejected(payload, bbox):
    payload["elements"][0]["bbox"] = bbox
    with pytest.raises(ValidationError):
        PerceptionResponse.model_validate(payload)


def test_duplicate_ids_cannot_be_used_as_action_targets(payload):
    payload["elements"].append(deepcopy(payload["elements"][0]))
    with pytest.raises(ValidationError, match="duplicate element id"):
        PerceptionResponse.model_validate(payload)


def test_unknown_action_is_not_silently_accepted(payload):
    payload["elements"][0]["actions"] = ["purchase"]
    with pytest.raises(ValidationError):
        PerceptionResponse.model_validate(payload)


def test_invalid_confidence_is_rejected(payload):
    payload["elements"][0]["confidence"] = 1.2
    with pytest.raises(ValidationError):
        PerceptionResponse.model_validate(payload)
