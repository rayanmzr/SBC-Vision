import pytest
from pydantic import ValidationError

from sbc_vision.contracts.perception import ActionKind, ImageSize, PerceptionResponse
from sbc_vision.perception.elements import to_elements

DETECTIONS = [
    ("link", (10.4, 20.6, 90.2, 31.1), 0.45),
    ("input", (100.0, 50.0, 400.0, 80.0), 0.93),
    ("button", (5.0, 5.0, 50.0, 25.0), 0.12),
]


def test_kept_detections_become_contract_elements():
    elements = to_elements(DETECTIONS, min_score=0.3)
    assert [(e.id, e.kind.value, e.confidence) for e in elements] == [
        ("e0", "input", 0.93),
        ("e1", "link", 0.45),
    ]
    assert elements[0].actions == [ActionKind.FILL]
    assert elements[1].actions == [ActionKind.CLICK]
    # Arrondi vers l'extérieur : la boîte entière reste couverte.
    box = elements[1].bbox
    assert (box.x, box.y, box.width, box.height) == (10, 20, 81, 12)
    response = PerceptionResponse(
        capture_id="c", image=ImageSize(width=1280, height=720), model_name="m", elements=elements
    )
    assert len(response.elements) == 2


def test_a_box_outside_the_capture_is_refused_by_the_contract():
    elements = to_elements([("button", (1270.0, 700.0, 1290.0, 719.0), 0.9)], min_score=0.3)
    with pytest.raises(ValidationError):
        PerceptionResponse(
            capture_id="c",
            image=ImageSize(width=1280, height=720),
            model_name="m",
            elements=elements,
        )
