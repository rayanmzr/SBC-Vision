"""Découpe un split en parties (entraînement, validation, test) selon une affectation par page.

    python -m sbc_vision.perception.datasets.split_corpus --corpus <corpus> --split near \
        --assignment data/manifests/near-split.json

L'affectation donne la partie de chaque page (`{"easysbc-03": "test", ...}`) ; toutes ses
captures la suivent. Écrit `{split}-{partie}.coco.json` et `.manifest.jsonl` à côté du split.
Une page sans partie, ou une partie pour une page absente, est une erreur.
"""

import argparse
import json
from dataclasses import replace
from pathlib import Path

from sbc_vision.perception.datasets.records import (
    BoxRecord,
    kind_from_category_id,
    read_manifest,
    write_corpus,
)


def split_corpus(corpus: Path, split: str, assignment: dict[str, str]) -> dict[str, int]:
    images = read_manifest(corpus / f"{split}.manifest.jsonl")
    groups = {image.group for image in images}
    if groups != set(assignment):
        missing, unknown = sorted(groups - set(assignment)), sorted(set(assignment) - groups)
        raise ValueError(f"affectation incomplète : sans partie {missing}, inconnues {unknown}")
    document = json.loads((corpus / f"{split}.coco.json").read_text(encoding="utf-8"))
    boxes_of: dict[int, list[BoxRecord]] = {}
    for annotation in sorted(document["annotations"], key=lambda a: a["id"]):
        x, y, w, h = annotation["bbox"]
        boxes_of.setdefault(annotation["image_id"], []).append(
            BoxRecord(
                annotation["image_id"],
                kind_from_category_id(annotation["category_id"]),
                (x, y, x + w, y + h),
                annotation.get("extra", {}),
            )
        )
    counts = {}
    for part in sorted(set(assignment.values())):
        name = f"{split}-{part}"
        records = [
            replace(image, split=name) for image in images if assignment[image.group] == part
        ]
        boxes = [box for image in records for box in boxes_of.get(image.image_id, [])]
        write_corpus(corpus, name, records, boxes)
        counts[name] = len(records)
    return counts


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--corpus", type=Path, required=True)
    parser.add_argument("--split", required=True)
    parser.add_argument("--assignment", type=Path, required=True)
    args = parser.parse_args()
    assignment = json.loads(args.assignment.read_text(encoding="utf-8"))
    print(json.dumps(split_corpus(args.corpus, args.split, assignment), indent=2))


if __name__ == "__main__":
    main()
