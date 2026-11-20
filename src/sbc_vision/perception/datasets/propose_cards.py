"""Propose les cartes de joueur et les emplacements d'un terrain, à revoir à la main.

    python -m sbc_vision.perception.datasets.propose_cards --corpus <corpus> --split near-auto \
        --data-root <captures> --out <propositions.json>

Le code d'une page ne connaît ni carte ni emplacement, mais une carte s'y affiche comme une
image nommée (le joueur) aux proportions d'une carte. Une telle image qui remplit un bouton
pré-annoté (le poste du terrain sur lequel on agit) fait de ce bouton un emplacement ; sinon,
elle devient une carte. Une image superposée à une carte déjà proposée est ignorée. La sortie a
le format des corrections (`corrections.py`) : elle se relit et se complète page par page.
"""

import argparse
import json
from pathlib import Path

import numpy as np

from sbc_vision.contracts.perception import ElementKind
from sbc_vision.perception.boxes import area, clip, intersection_matrix, iou_matrix
from sbc_vision.perception.datasets.records import BoxRecord, ImageRecord, read_corpus
from sbc_vision.perception.datasets.webui import WebUIPage

CARD_ASPECT = (0.6, 0.8)  # largeur / hauteur d'une carte
MIN_CARD_HEIGHT = 50  # pixels de la capture
MIN_VISIBLE = 0.5
SLOT_COVER = 0.9  # part de la carte dans le bouton
SLOT_FILL = 0.6  # part du bouton couverte par la carte
SAME_CARD_IOU = 0.8
NOT_A_PLAYER = ("pack", "récompense", "reward", "logo", "badge", "icon", "coin", "crest", "flag")


def card_images(page: WebUIPage, record: ImageRecord) -> np.ndarray:
    """Boîtes des images de carte de la page, rognées à la capture, sans superpositions."""
    boxes = page.node_boxes()
    cards = []
    for node in page.accessibility_tree()["nodes"]:
        name = str(node.get("name", {}).get("value", "")).lower()
        rect = boxes.get(str(node.get("backendDOMNodeId")))
        if node.get("ignored") or node.get("role", {}).get("value") not in ("image", "img"):
            continue
        if not name or not rect or any(word in name for word in NOT_A_PLAYER):
            continue
        x, y = rect["x"] * record.scale, rect["y"] * record.scale
        w, h = rect["width"] * record.scale, rect["height"] * record.scale
        if h >= MIN_CARD_HEIGHT and CARD_ASPECT[0] <= w / h <= CARD_ASPECT[1]:
            cards.append((x, y, x + w, y + h))
    if not cards:
        return np.zeros((0, 4))
    cards = np.array(cards)
    visible = clip(cards, record.width, record.height)
    cards = visible[area(visible) >= MIN_VISIBLE * area(cards)]
    kept: list[np.ndarray] = []
    for card in cards:
        if not kept or not (iou_matrix(card[None], np.array(kept)) >= SAME_CARD_IOU).any():
            kept.append(card)
    return np.array(kept).reshape(-1, 4)


def propose(record: ImageRecord, boxes: list[BoxRecord], cards: np.ndarray) -> dict:
    buttons = [rank for rank, box in enumerate(boxes) if box.kind is ElementKind.BUTTON]
    button_boxes = np.array([boxes[rank].box for rank in buttons]).reshape(-1, 4)
    inter = intersection_matrix(cards, button_boxes)
    relabel, add = {}, []
    for index, card in enumerate(cards):
        cover = inter[index] / area(card[None])[0]
        fill = inter[index] / np.maximum(area(button_boxes), 1)
        hosts = np.flatnonzero((cover >= SLOT_COVER) & (fill >= SLOT_FILL))
        if len(hosts):
            relabel[str(buttons[hosts[-1]])] = ElementKind.SLOT.value
        else:
            add.append({"kind": ElementKind.CARD.value, "box": [round(v, 1) for v in card]})
    return {key: value for key, value in (("relabel", relabel), ("add", add)) if value}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--corpus", type=Path, required=True)
    parser.add_argument("--split", required=True)
    parser.add_argument("--data-root", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    corpus = read_corpus(args.corpus, args.split)
    proposals = {}
    for record in corpus.images:
        page = WebUIPage.from_record(record, args.data_root)
        fix = propose(record, corpus.boxes[record.image_id], card_images(page, record))
        if fix:
            proposals[record.group] = fix
    args.out.write_text(json.dumps(proposals, indent=1, ensure_ascii=False) + "\n")
    print(json.dumps({"pages": len(proposals)}))


if __name__ == "__main__":
    main()
