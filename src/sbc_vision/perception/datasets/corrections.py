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
import gzip
import json
from dataclasses import replace
from pathlib import Path

import numpy as np

from sbc_vision.contracts.perception import ElementKind
from sbc_vision.perception.boxes import iou_matrix
from sbc_vision.perception.datasets.records import (
    BoxRecord,
    kind_from_category_id,
    read_manifest,
    write_corpus,
)

SNAP_IOU = 0.5


def _page_boxes(capture: Path, scale: float) -> list[tuple[float, float, float, float]]:
    """Boîtes de tous les éléments mis en page, en pixels de la capture."""
    device = capture.name.removesuffix("-screenshot.webp")
    with gzip.open(capture.with_name(f"{device}-bb.json.gz"), "rt", encoding="utf-8") as handle:
        boxes = json.load(handle)
    return [
        (
            b["x"] * scale,
            b["y"] * scale,
            (b["x"] + b["width"]) * scale,
            (b["y"] + b["height"]) * scale,
        )
        for b in boxes.values()
        if b["width"] > 0 and b["height"] > 0
    ]


def snap(near: tuple[float, ...], candidates: list[tuple[float, ...]]) -> tuple[float, ...]:
    overlaps = iou_matrix(np.array([near]), np.array(candidates).reshape(-1, 4))[0]
    best = int(overlaps.argmax())
    if overlaps[best] < SNAP_IOU:
        raise ValueError(
            f"aucun élément de la page ne recouvre {near} (meilleur IoU {overlaps[best]:.2f})"
        )
    return tuple(float(v) for v in candidates[best])


def apply_corrections(
    corpus: Path, split: str, out_split: str, data_root: Path, corrections: dict
) -> dict:
    document = json.loads((corpus / f"{split}.coco.json").read_text(encoding="utf-8"))
    images = read_manifest(corpus / f"{split}.manifest.jsonl")
    per_image: dict[int, list[dict]] = {}
    for annotation in sorted(document["annotations"], key=lambda a: a["id"]):
        per_image.setdefault(annotation["image_id"], []).append(annotation)
    unknown = set(corrections) - {image.group for image in images}
    if unknown:
        raise ValueError(f"corrections pour des pages absentes du split : {sorted(unknown)}")

    boxes: list[BoxRecord] = []
    counts = {"kept": 0, "removed": 0, "relabeled": 0, "added": 0}
    for image in images:
        fix = corrections.get(image.group, {})
        removed = set(fix.get("remove", []))
        relabel = {int(rank): ElementKind(kind) for rank, kind in fix.get("relabel", {}).items()}
        annotations = per_image.get(image.image_id, [])
        if any(rank >= len(annotations) for rank in removed | set(relabel)):
            raise ValueError(f"{image.group} : rang de boîte hors limites")
        for rank, annotation in enumerate(annotations):
            if rank in removed:
                counts["removed"] += 1
                continue
            x, y, w, h = annotation["bbox"]
            kind = relabel.get(rank, kind_from_category_id(annotation["category_id"]))
            counts["relabeled" if rank in relabel else "kept"] += 1
            extra = {
                **annotation.get("extra", {}),
                **({"relabeled": True} if rank in relabel else {}),
            }
            boxes.append(BoxRecord(image.image_id, kind, (x, y, x + w, y + h), extra))
        candidates = None
        for added in fix.get("add", []):
            if "box" in added:
                box = tuple(added["box"])
            else:
                if candidates is None:
                    candidates = _page_boxes(data_root / image.file_name, image.extra["scale"])
                box = snap(tuple(added["near"]), candidates)
            boxes.append(
                BoxRecord(image.image_id, ElementKind(added["kind"]), box, {"added": True})
            )
            counts["added"] += 1
    records = [replace(image, split=out_split) for image in images]
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
