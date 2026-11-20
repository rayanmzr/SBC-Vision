"""Exporte des sous-ensembles du corpus au format YOLO (Ultralytics), sans copier les images.

    python -m sbc_vision.perception.datasets.export_yolo \
        --corpus <corpus> \
        --data-root <extrait> \
        --out <exports>/webui-desktop \
        --train train:all --val val:500 --near-duplicate-max 18

Chaque `--train`/`--val` vaut `split:nombre`. `all` garde toutes les captures du split (les
quatre tailles d'écran de chaque page : des variantes d'échelle) ; un nombre prend le
sous-ensemble d'évaluation (une capture par site), le même que celui de `evaluate`. `--add`
ajoute à l'entraînement ou à la validation toutes les captures d'un split d'un autre corpus,
répétées pour peser davantage (adaptation à un petit corpus, par exemple EasySBC) :

    --add train <corpus-near> <captures-near> near-train 30

Les images sont liées en dur (même disque), les étiquettes écrites en coordonnées normalisées.
L'indice de classe YOLO est l'indice dans `DETECTOR_CLASSES`.
"""

import argparse
import json
import os
from pathlib import Path

from sbc_vision.perception.datasets.records import BoxRecord, ImageRecord, read_corpus
from sbc_vision.perception.datasets.subsets import evaluation_subset
from sbc_vision.perception.ontology import DETECTOR_CLASSES, class_id


def write_part(
    name: str,
    split: str,
    records: list[ImageRecord],
    boxes: dict[int, list[BoxRecord]],
    data_root: Path,
    out: Path,
    repeat: int,
) -> dict:
    images_dir, labels_dir = out / "images" / name, out / "labels" / name
    images_dir.mkdir(parents=True, exist_ok=True)
    labels_dir.mkdir(parents=True, exist_ok=True)
    count = 0
    for record in records:
        source = data_root / record.file_name
        lines = []
        for box in boxes[record.image_id]:
            x1, y1, x2, y2 = box.box
            cx, cy = (x1 + x2) / 2 / record.width, (y1 + y2) / 2 / record.height
            w, h = (x2 - x1) / record.width, (y2 - y1) / record.height
            lines.append(f"{class_id(box.kind)} {cx:.6f} {cy:.6f} {w:.6f} {h:.6f}")
        for copy in range(repeat):
            stem = f"{split}-{record.image_id:07d}" + (f"-r{copy:02d}" if repeat > 1 else "")
            os.link(source, images_dir / f"{stem}{source.suffix}")  # deux sources : erreur
            (labels_dir / f"{stem}.txt").write_text("\n".join(lines), encoding="utf-8")
        count += len(lines) * repeat
    return {"images": len(records) * repeat, "boxes": count}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--corpus", type=Path, required=True)
    parser.add_argument("--data-root", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True, help="dossier à créer (pas d'existant)")
    parser.add_argument("--train", required=True)
    parser.add_argument("--val", required=True)
    parser.add_argument("--near-duplicate-max", type=int)
    parser.add_argument(
        "--add",
        nargs=5,
        action="append",
        default=[],
        metavar=("PART", "CORPUS", "DATA_ROOT", "SPLIT", "REPEAT"),
        help="ajoute toutes les captures d'un split d'un autre corpus à train ou val",
    )
    args = parser.parse_args()
    args.out.mkdir(parents=True)  # un export existant n'est jamais complété ni réécrit
    summary = {}
    for name, spec in (("train", args.train), ("val", args.val)):
        split, count = spec.split(":")
        corpus = read_corpus(args.corpus, split)
        if count == "all":
            records = corpus.images
        else:
            # Les quasi-doublons de l'entraînement ne s'écartent que de la validation.
            near_duplicate_max = args.near_duplicate_max if name == "val" else None
            subset = evaluation_subset(
                args.corpus, split, int(count), 0, near_duplicate_max, "domain"
            )
            records = subset.records
        written = write_part(name, split, records, corpus.boxes, args.data_root, args.out, 1)
        summary[name] = {"spec": spec, **written}
    for part, corpus_dir, data_root, split, repeat in args.add:
        if part not in summary:
            raise ValueError(f"partie inconnue : {part}")
        corpus = read_corpus(Path(corpus_dir), split)
        written = write_part(
            part, split, corpus.images, corpus.boxes, Path(data_root), args.out, int(repeat)
        )
        summary[part].setdefault("added", []).append(
            {"corpus": corpus_dir, "split": split, "repeat": int(repeat), **written}
        )
    names = "\n".join(f"  {i}: {kind.value}" for i, kind in enumerate(DETECTOR_CLASSES))
    (args.out / "data.yaml").write_text(
        f"train: images/train\nval: images/val\nnames:\n{names}\n", encoding="utf-8"
    )
    (args.out / "export.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
