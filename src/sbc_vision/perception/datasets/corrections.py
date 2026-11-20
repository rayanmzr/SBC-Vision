"""Applique les corrections manuelles à un split pré-annoté par le code de la page.

    python -m sbc_vision.perception.datasets.corrections --corpus <corpus> \
        --split ood-auto --out-split ood --data-root <captures> \
        --corrections data/manifests/ood-corrections.json

Les corrections sont rangées par page (dossier de capture) :

    {"ldlc-00": {"remove": [3, 7], "relabel": {"5": "button"},
                 "add": [{"kind": "menu", "near": [0, 80, 200, 120]}]}}

`remove` et `relabel` désignent les boîtes pré-annotées de la capture par leur rang (ordre du
fichier COCO). Une boîte ajoutée vaut `box` (coordonnées exactes, en pixels de la capture) ou
`near` (zone approximative, recalée sur la boîte de l'élément de la page qui la recouvre le
mieux) ; un recalage sans élément assez proche est une erreur, pas une approximation.
Voir docs/ANNOTATION.md pour ce qu'on boîte et avec quelle classe.
"""

import argparse
import json
from dataclasses import replace
from pathlib import Path

import numpy as np

from sbc_vision.contracts.perception import ElementKind
from sbc_vision.perception.boxes import iou_matrix
from sbc_vision.perception.datasets.records import BoxRecord, read_corpus, write_corpus
from sbc_vision.perception.datasets.webui import WebUIPage

SNAP_IOU = 0.5
PAGE_KEYS = {"remove", "relabel", "add", "note"}
ADD_KEYS = ({"kind", "box"}, {"kind", "near"})


def snap(near: tuple[float, ...], candidates: list[tuple[float, ...]]) -> tuple[float, ...]:
    overlaps = iou_matrix(np.array([near]), np.array(candidates).reshape(-1, 4))[0]
    best = int(overlaps.argmax())
    if overlaps[best] < SNAP_IOU:
        raise ValueError(
            f"aucun élément de la page ne recouvre {near} (meilleur IoU {overlaps[best]:.2f})"
        )
    return tuple(float(v) for v in candidates[best])


def _check(page: str, fix: dict, n_boxes: int) -> None:
    if set(fix) - PAGE_KEYS:
        raise ValueError(f"{page} : clés inconnues {sorted(set(fix) - PAGE_KEYS)}")
    ranks = set(fix.get("remove", [])) | {int(rank) for rank in fix.get("relabel", {})}
    if any(not 0 <= rank < n_boxes for rank in ranks):
        raise ValueError(f"{page} : rang de boîte hors limites")
    if any(set(added) not in ADD_KEYS for added in fix.get("add", [])):
        raise ValueError(f"{page} : un ajout demande `kind` et soit `box`, soit `near`")


def apply_corrections(
    corpus: Path, split: str, out_split: str, data_root: Path, corrections: dict
) -> dict:
    source = read_corpus(corpus, split)
    unknown = set(corrections) - {image.group for image in source.images}
    if unknown:
        raise ValueError(f"corrections pour des pages absentes du split : {sorted(unknown)}")

    boxes: list[BoxRecord] = []
    counts = {"kept": 0, "removed": 0, "relabeled": 0, "added": 0}
    for image in source.images:
        page_boxes = source.boxes[image.image_id]
        # Une page sans entrée n'a rien à corriger.
        fix = corrections.get(image.group, {})
        _check(image.group, fix, len(page_boxes))
        removed = set(fix.get("remove", []))
        relabel = {int(rank): ElementKind(kind) for rank, kind in fix.get("relabel", {}).items()}
        for rank, box in enumerate(page_boxes):
            if rank in removed:
                counts["removed"] += 1
            elif rank in relabel:
                counts["relabeled"] += 1
                boxes.append(
                    replace(box, kind=relabel[rank], extra={**box.extra, "relabeled": True})
                )
            else:
                counts["kept"] += 1
                boxes.append(box)
        layout = None
        for added in fix.get("add", []):
            if "box" in added:
                box = tuple(added["box"])
            else:
                if layout is None:
                    layout = WebUIPage.from_record(image, data_root).layout_boxes(image.scale)
                box = snap(tuple(added["near"]), layout)
            boxes.append(
                BoxRecord(image.image_id, ElementKind(added["kind"]), box, {"added": True})
            )
            counts["added"] += 1
    records = [replace(image, split=out_split) for image in source.images]
    write_corpus(corpus, out_split, records, boxes)
    return {"images": len(records), "boxes": len(boxes), **counts}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--corpus", type=Path, required=True)
    parser.add_argument("--split", required=True)
    parser.add_argument("--out-split", required=True)
    parser.add_argument("--data-root", type=Path, required=True)
    parser.add_argument("--corrections", type=Path, required=True)
    args = parser.parse_args()
    corrections = json.loads(args.corrections.read_text(encoding="utf-8"))
    summary = apply_corrections(
        args.corpus, args.split, args.out_split, args.data_root, corrections
    )
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
