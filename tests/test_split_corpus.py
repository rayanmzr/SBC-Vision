import json

import pytest

from sbc_vision.contracts.perception import ElementKind
from sbc_vision.perception.datasets.records import BoxRecord, ImageRecord, write_corpus
from sbc_vision.perception.datasets.split_corpus import split_corpus


def image(image_id, group):
    return ImageRecord(
        image_id, f"{group}/a.webp", 100, 100, "capture", "near", "x.org", group, "d", "0", 1.0
    )


@pytest.fixture
def corpus(tmp_path):
    images = [image(1, "p-00"), image(2, "p-01"), image(3, "p-02")]
    boxes = [BoxRecord(i, ElementKind.BUTTON, (0, 0, 10, 10)) for i in (1, 2, 3)]
    boxes.append(BoxRecord(3, ElementKind.SLOT, (20, 20, 40, 50)))
    write_corpus(tmp_path, "near", images, boxes)
    return tmp_path


def test_each_page_and_its_boxes_follow_their_part(corpus):
    counts = split_corpus(corpus, "near", {"p-00": "train", "p-01": "train", "p-02": "test"})
    assert counts == {"near-test": 1, "near-train": 2}
    test = json.loads((corpus / "near-test.coco.json").read_text())
    assert [i["file_name"] for i in test["images"]] == ["p-02/a.webp"]
    assert sorted(a["category_id"] for a in test["annotations"]) == [1, 7]


def test_assignment_must_cover_exactly_the_pages(corpus):
    with pytest.raises(ValueError):
        split_corpus(corpus, "near", {"p-00": "train", "p-01": "test"})
    with pytest.raises(ValueError):
        split_corpus(corpus, "near", {"p-00": "train", "p-01": "test", "p-02": "test", "p-09": "x"})
