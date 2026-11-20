"""Quasi-doublons entre splits : un même modèle de site publié sous plusieurs domaines.

WebUI sépare ses splits par nom de domaine, mais des sites clonés (même gabarit, autres produits)
existent sous des domaines différents : sans contrôle, le test contiendrait des pages déjà vues à
l'entraînement. Chaque page est résumée par une empreinte de gradient (dHash 16 × 9, 144 bits)
de sa capture d'ordinateur ; une page de validation ou de test trop proche d'une page
d'entraînement est écartée de l'évaluation.

    python -m sbc_vision.perception.datasets.near_duplicates \
        --corpus <corpus> \
        --data-root <extrait> --reference train --check val test
"""

import argparse
import json
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

import numpy as np
from PIL import Image

from sbc_vision.perception.datasets.records import ImageRecord, read_manifest
from sbc_vision.perception.datasets.webui import DESKTOP_DEVICES

HASH_SIZE = (16, 9)
PREFERRED_DEVICE = DESKTOP_DEVICES[0]


def dhash(path: Path) -> np.ndarray:
    width, height = HASH_SIZE
    with Image.open(path) as image:
        gray = image.convert("L").resize((width + 1, height), Image.BILINEAR)
    pixels = np.asarray(gray, dtype=np.int16)
    return pixels[:, 1:] > pixels[:, :-1]


def near_duplicate_groups(corpus: Path, split: str, max_distance: int) -> set[str]:
    """Pages du split à `max_distance` bits ou moins d'une page d'entraînement."""
    path = corpus / f"{split}.near_duplicates.jsonl"
    rows = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]
    return {row["group"] for row in rows if row["distance"] <= max_distance}


def page_representatives(records: list[ImageRecord]) -> dict[str, ImageRecord]:
    """Une capture par page, la même résolution partout quand elle existe."""
    chosen: dict[str, ImageRecord] = {}
    for record in records:
        current = chosen.get(record.group)
        if current is None or (
            record.device == PREFERRED_DEVICE and current.device != PREFERRED_DEVICE
        ):
            chosen[record.group] = record
    return chosen


def hash_pages(records: dict[str, ImageRecord], data_root: Path, workers: int):
    groups = sorted(records)
    paths = [data_root / records[group].file_name for group in groups]
    with ProcessPoolExecutor(max_workers=workers) as pool:
        hashes = list(pool.map(dhash, paths, chunksize=64))
    return groups, np.packbits(np.array(hashes).reshape(len(groups), -1), axis=1)


def nearest(queries: np.ndarray, reference: np.ndarray, chunk: int = 256):
    """Distance de Hamming minimale de chaque requête à la référence, et l'indice atteint."""
    table = np.array([bin(i).count("1") for i in range(256)], dtype=np.uint8)
    best = np.empty(len(queries), dtype=np.int32)
    where = np.empty(len(queries), dtype=np.int64)
    for start in range(0, len(queries), chunk):
        part = queries[start : start + chunk]
        distances = table[part[:, None, :] ^ reference[None, :, :]].sum(axis=2, dtype=np.int32)
        best[start : start + chunk] = distances.min(axis=1)
        where[start : start + chunk] = distances.argmin(axis=1)
    return best, where


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--corpus", type=Path, required=True)
    parser.add_argument("--data-root", type=Path, required=True)
    parser.add_argument("--reference", default="train")
    parser.add_argument("--check", nargs="+", required=True)
    parser.add_argument("--workers", type=int, default=3)
    args = parser.parse_args()

    def load(split):
        reps = page_representatives(read_manifest(args.corpus / f"{split}.manifest.jsonl"))
        groups, hashes = hash_pages(reps, args.data_root, args.workers)
        return reps, groups, hashes

    ref_reps, ref_groups, ref_hashes = load(args.reference)
    for split in args.check:
        reps, groups, hashes = load(split)
        distance, index = nearest(hashes, ref_hashes)
        rows = [
            {
                "group": group,
                "domain": reps[group].domain,
                "distance": int(d),
                "nearest_group": ref_groups[i],
                "nearest_domain": ref_reps[ref_groups[i]].domain,
            }
            for group, d, i in zip(groups, distance, index, strict=True)
        ]
        out = args.corpus / f"{split}.near_duplicates.jsonl"
        out.write_text("".join(json.dumps(row) + "\n" for row in rows), encoding="utf-8")
        histogram = np.bincount(np.minimum(distance, 80) // 5, minlength=17)
        print(split, "pages", len(rows), "histogram by 5 bits:", histogram.tolist())


if __name__ == "__main__":
    main()
