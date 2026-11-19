"""Entraîne le classifieur de l'approche A sur les propositions d'un sous-ensemble du corpus.

    python -m sbc_vision.perception.baselines.train_opencv \
        --corpus <corpus> --split train \
        --data-root <extrait> --images 1500 \
        --out models/opencv-gbdt.pkl

Étiquette d'une proposition : la classe de la vérité de meilleur IoU s'il atteint 0,5, le fond
s'il reste sous 0,3 ; entre les deux, la proposition est ignorée (ni positive ni négative).
Le fond est sous-échantillonné (trois fois les positives de l'image, au moins 50).
"""

import argparse
import json
import time
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

import numpy as np
from PIL import Image
from sklearn.ensemble import HistGradientBoostingClassifier

from sbc_vision.perception.baselines.opencv_baseline import (
    BACKGROUND,
    FEATURE_NAMES,
    OpenCVBaseline,
    features,
    propose,
)
from sbc_vision.perception.datasets.records import read_manifest
from sbc_vision.perception.datasets.subsets import one_per_group
from sbc_vision.perception.evaluation.metrics import iou_matrix
from sbc_vision.perception.evaluation.runner import load_ground_truth

POSITIVE_IOU = 0.5
NEGATIVE_IOU = 0.3


def _image_samples(args):
    path, gt_kinds, gt_boxes, seed = args
    with Image.open(path) as source:
        rgb = np.asarray(source.convert("RGB"))
    boxes, origin, maps = propose(rgb)
    if len(boxes) == 0:
        return np.zeros((0, len(FEATURE_NAMES)), np.float32), []
    x = features(boxes, origin, maps)
    if len(gt_boxes):
        ious = iou_matrix(boxes.astype(np.float64), np.asarray(gt_boxes))
        best, arg = ious.max(axis=1), ious.argmax(axis=1)
    else:
        best, arg = np.zeros(len(boxes)), np.zeros(len(boxes), dtype=int)
    positive = np.flatnonzero(best >= POSITIVE_IOU)
    negative = np.flatnonzero(best < NEGATIVE_IOU)
    rng = np.random.default_rng(seed)
    n_negative = min(len(negative), max(50, 3 * len(positive)))
    negative = rng.choice(negative, n_negative, replace=False) if n_negative else negative[:0]
    rows = np.concatenate([positive, negative])
    labels = [gt_kinds[arg[i]] for i in positive] + [BACKGROUND] * len(negative)
    return x[rows], labels


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--corpus", type=Path, required=True)
    parser.add_argument("--split", default="train")
    parser.add_argument("--data-root", type=Path, required=True)
    parser.add_argument("--images", type=int, default=1500)
    parser.add_argument("--seed", type=int, default=0)
    parser.add_argument("--workers", type=int, default=3)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()

    truth = load_ground_truth(args.corpus / f"{args.split}.coco.json")
    records = one_per_group(
        read_manifest(args.corpus / f"{args.split}.manifest.jsonl"),
        args.images,
        args.seed,
        key="group",
    )
    jobs = [
        (
            args.data_root / record.file_name,
            truth.boxes[record.image_id].kinds,
            truth.boxes[record.image_id].boxes,
            args.seed + record.image_id,
        )
        for record in records
    ]
    started = time.perf_counter()
    with ProcessPoolExecutor(max_workers=args.workers) as pool:
        parts = list(pool.map(_image_samples, jobs, chunksize=8))
    x = np.vstack([part[0] for part in parts])
    y = np.array([label for part in parts for label in part[1]])
    extraction_s = time.perf_counter() - started

    classifier = HistGradientBoostingClassifier(
        max_iter=400,
        learning_rate=0.1,
        max_leaf_nodes=63,
        l2_regularization=1.0,
        early_stopping=True,
        validation_fraction=0.1,
        random_state=args.seed,
    )
    started = time.perf_counter()
    classifier.fit(x, y)
    fit_s = time.perf_counter() - started
    detector = OpenCVBaseline(classifier, tuple(classifier.classes_))
    detector.save(args.out)
    labels, counts = np.unique(y, return_counts=True)
    info = {
        "images": len(records),
        "seed": args.seed,
        "samples": int(len(y)),
        "per_label": dict(zip(labels.tolist(), counts.tolist(), strict=True)),
        "iterations": int(classifier.n_iter_),
        "extraction_seconds": round(extraction_s, 1),
        "fit_seconds": round(fit_s, 1),
        "image_ids": [record.image_id for record in records],
    }
    args.out.with_suffix(".train.json").write_text(json.dumps(info, indent=2), encoding="utf-8")
    print(json.dumps({k: v for k, v in info.items() if k != "image_ids"}, indent=2))


if __name__ == "__main__":
    main()
