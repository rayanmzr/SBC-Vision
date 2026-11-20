import gzip
import json

import numpy as np

from sbc_vision.contracts.perception import ElementKind
from sbc_vision.perception.datasets.propose_cards import card_images, propose
from sbc_vision.perception.datasets.records import BoxRecord, ImageRecord
from sbc_vision.perception.datasets.webui import WebUIPage

DEVICE = "default_1280-720"


def node(backend, role, name):
    return {
        "nodeId": str(backend),
        "ignored": False,
        "role": {"value": role},
        "name": {"value": name},
        "backendDOMNodeId": backend,
    }


def test_a_card_filling_a_pitch_button_makes_it_a_slot(tmp_path):
    nodes = [
        node(1, "RootWebArea", "page"),
        node(2, "image", "Esposito"),  # dans un poste du terrain
        node(3, "image", "Esposito"),  # même image superposée
        node(4, "image", "Bonansea"),  # carte seule
        node(5, "image", "Pack Or"),  # paquet, pas un joueur
    ]
    boxes = {
        "1": {"x": 0, "y": 0, "width": 1280, "height": 720},
        "2": {"x": 100, "y": 100, "width": 119, "height": 167},
        "3": {"x": 100, "y": 101, "width": 119, "height": 167},
        "4": {"x": 600, "y": 100, "width": 119, "height": 167},
        "5": {"x": 900, "y": 100, "width": 119, "height": 167},
    }
    for kind, value in (("axtree.json.gz", {"nodes": nodes}), ("bb.json.gz", boxes)):
        with gzip.open(tmp_path / f"{DEVICE}-{kind}", "wt") as handle:
            json.dump(value, handle)
    record = ImageRecord(
        1,
        f"{DEVICE}-screenshot.webp",
        1280,
        720,
        "capture",
        "auto",
        "x.org",
        "p",
        DEVICE,
        "0",
        1.0,
        extra={"url": "https://x.org/"},
    )
    page = WebUIPage("p", DEVICE, tmp_path / f"{DEVICE}-screenshot.webp", "https://x.org/")
    cards = card_images(page, record)
    assert len(cards) == 2
    pre = [
        BoxRecord(1, ElementKind.LINK, (0, 0, 50, 20)),
        BoxRecord(
            1, ElementKind.BUTTON, (100, 100, 219, 282)
        ),  # le poste, bouton « Marché » compris
    ]
    fix = propose(record, pre, cards)
    assert fix["relabel"] == {"1": "slot"}
    assert [a["kind"] for a in fix["add"]] == ["card"]
    assert np.allclose(fix["add"][0]["box"], [600, 100, 719, 267])
