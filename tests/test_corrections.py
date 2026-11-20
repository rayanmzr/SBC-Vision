import gzip
import json

import pytest

from sbc_vision.contracts.perception import ElementKind
from sbc_vision.perception.datasets.corrections import apply_corrections
from sbc_vision.perception.datasets.records import BoxRecord, ImageRecord, write_corpus

PAGE = "site-00"
CAPTURE = f"{PAGE}/default_1280-720-screenshot.webp"


@pytest.fixture
def corpus(tmp_path):
    image = ImageRecord(
        1,
        CAPTURE,
        1280,
        720,
        "capture",
        "auto",
        "site.org",
        PAGE,
        "default_1280-720",
        "0" * 64,
        scale=1.0,
        extra={"url": "https://site.org/"},
    )
    boxes = [
        BoxRecord(1, ElementKind.LINK, (10, 10, 110, 30)),
        BoxRecord(1, ElementKind.LINK, (10, 50, 110, 70)),
        BoxRecord(1, ElementKind.INPUT, (200, 10, 400, 40)),
    ]
    write_corpus(tmp_path, "auto", [image], boxes)
    # Un bouton que le code de la page ne déclarait pas : un simple div cliquable.
    (tmp_path / PAGE).mkdir()
    with gzip.open(tmp_path / PAGE / "default_1280-720-bb.json.gz", "wt") as handle:
        json.dump({"7": {"x": 500, "y": 100, "width": 120, "height": 40}}, handle)
    return tmp_path


def read(corpus, split):
    document = json.loads((corpus / f"{split}.coco.json").read_text())
    return [(a["category_id"], a["bbox"]) for a in document["annotations"]]


def test_remove_relabel_and_snapped_addition(corpus):
    fixes = {
        PAGE: {
            "remove": [0],
            "relabel": {"1": "button"},
            "add": [{"kind": "menu", "near": [505, 98, 615, 138]}],
        }
    }
    summary = apply_corrections(corpus, "auto", "verified", corpus, fixes)
    assert summary == {"images": 1, "boxes": 3, "kept": 1, "removed": 1, "relabeled": 1, "added": 1}
    assert read(corpus, "verified") == [
        (1, [10, 50, 100, 20]),  # lien devenu bouton (catégorie 1)
        (2, [200, 10, 200, 30]),
        (4, [500, 100, 120, 40]),  # recalé sur la boîte exacte de l'élément
    ]


def test_addition_far_from_any_element_is_refused(corpus):
    with pytest.raises(ValueError):
        apply_corrections(
            corpus,
            "auto",
            "verified",
            corpus,
            {PAGE: {"add": [{"kind": "button", "near": [0, 600, 50, 650]}]}},
        )


def test_corrections_for_unknown_pages_are_refused(corpus):
    with pytest.raises(ValueError):
        apply_corrections(corpus, "auto", "verified", corpus, {"other-00": {"remove": [0]}})


def test_unknown_keys_are_refused(corpus):
    with pytest.raises(ValueError):
        apply_corrections(corpus, "auto", "verified", corpus, {PAGE: {"relable": {"0": "button"}}})
    with pytest.raises(ValueError):
        apply_corrections(corpus, "auto", "verified", corpus, {PAGE: {"add": [{"kind": "menu"}]}})
