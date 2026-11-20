"""Faire tourner un détecteur sur un split, puis mesurer ses prédictions.

Toutes les approches passent par la même interface (`Detector`) et le même rapport : seules
leurs prédictions changent. Le seuil de score du point de fonctionnement est choisi sur la
validation (meilleur F1) et réutilisé tel quel sur les tests.
"""

import json
import time
from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from pathlib import Path

import numpy as np
from PIL import Image

from sbc_vision.perception.datasets.records import ImageRecord, kind_from_category_id
from sbc_vision.perception.detector import Detector
from sbc_vision.perception.evaluation.metrics import (
    ImageBoxes,
    MatchedSet,
    bootstrap_interval,
    confusion_matrix,
    match_dataset,
)
from sbc_vision.perception.ontology import DETECTOR_CLASSES


@dataclass
class GroundTruth:
    images: list[dict]  # entrées COCO, dans l'ordre du fichier
    boxes: dict[int, ImageBoxes]


def load_ground_truth(coco_path: Path) -> GroundTruth:
    document = json.loads(coco_path.read_text(encoding="utf-8"))
    per_image: dict[int, tuple[list[str], list[list[float]]]] = {
        image["id"]: ([], []) for image in document["images"]
    }
    for annotation in document["annotations"]:
        x, y, w, h = annotation["bbox"]
        kinds, boxes = per_image[annotation["image_id"]]
        kinds.append(kind_from_category_id(annotation["category_id"]).value)
        boxes.append([x, y, x + w, y + h])
    return GroundTruth(
        images=document["images"],
        boxes={i: ImageBoxes(kinds, boxes) for i, (kinds, boxes) in per_image.items()},
    )


def run_detector(
    detector: Detector,
    images: Iterable[dict],
    data_root: Path,
    out_path: Path,
) -> None:
    """Écrit une ligne JSON par image : détections et latence de `detect` (ms)."""
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with out_path.open("w", encoding="utf-8") as handle:
        for image in images:
            with Image.open(data_root / image["file_name"]) as source:
                pixels = np.asarray(source.convert("RGB"))
            started = time.perf_counter()
            detections = detector.detect(pixels)
            latency_ms = (time.perf_counter() - started) * 1000
            handle.write(
                json.dumps(
                    {
                        "image_id": image["id"],
                        "latency_ms": round(latency_ms, 2),
                        "detections": [
                            {"kind": kind, "box": [round(v, 2) for v in box], "score": score}
                            for kind, box, score in detections
                        ],
                    }
                )
                + "\n"
            )


def load_predictions(path: Path) -> tuple[dict[int, ImageBoxes], dict[int, float]]:
    predictions, latencies = {}, {}
    with path.open(encoding="utf-8") as handle:
        for line in handle:
            row = json.loads(line)
            detections = row["detections"]
            predictions[row["image_id"]] = ImageBoxes(
                kinds=[d["kind"] for d in detections],
                boxes=[d["box"] for d in detections],
                scores=[d["score"] for d in detections],
            )
            latencies[row["image_id"]] = row["latency_ms"]
    return predictions, latencies


def best_f1_threshold(matched: MatchedSet) -> float:
    candidates = np.unique(
        np.concatenate(
            [part.scores for image in matched.images for part in image.labels.values()]
            or [np.zeros(0)]
        )
    )
    best, best_f1 = 0.5, -1.0
    for threshold in np.quantile(candidates, np.linspace(0, 1, 201)) if len(candidates) else []:
        f1 = matched.operating_point(float(threshold))["_all"]["f1"]
        if f1 > best_f1:
            best, best_f1 = float(threshold), f1
    return best


def evaluate(
    truth: GroundTruth,
    predictions: dict[int, ImageBoxes],
    latencies: dict[int, float],
    manifest: Sequence[ImageRecord],
    threshold: float | None = None,
    bootstrap_samples: int = 500,
    bootstrap_by: str = "domain",
) -> dict:
    """Rapport complet. Le bootstrap rééchantillonne des sites (`domain`) ou, pour un test
    tiré d'un seul site, des pages (`group`)."""
    image_ids = [image["id"] for image in truth.images if image["id"] in predictions]
    gts = [truth.boxes[i] for i in image_ids]
    preds = [predictions[i] for i in image_ids]
    records = {record.image_id: record for record in manifest}
    groups = [getattr(records[i], bootstrap_by) for i in image_ids]

    levels = {
        level: match_dataset(gts, preds, level) for level in ("kind", "action", "interactive")
    }
    source = "argument" if threshold is not None else "best F1 on this split"
    if threshold is None:
        threshold = best_f1_threshold(levels["kind"])
    report: dict = {"images": len(image_ids), "threshold": threshold, "threshold_source": source}
    for level, matched in levels.items():
        summary = matched.summary()
        low, high = bootstrap_interval(
            lambda idx, m=matched: m.summary(idx)["mAP50"],
            len(image_ids),
            groups,
            samples=bootstrap_samples,
        )
        report[level] = {
            **summary,
            "mAP50_ci95": [low, high],
            "operating_point": matched.operating_point(threshold),
        }
    report["recall_by_size"] = levels["interactive"].recall_by_size(threshold)
    classes = [kind.value for kind in DETECTOR_CLASSES]
    report["confusion"] = {
        "classes": classes + ["background"],
        "matrix": confusion_matrix(gts, preds, classes, threshold).tolist(),
    }
    values = np.array([latencies[i] for i in image_ids])
    report["latency_ms"] = {
        "p50": float(np.percentile(values, 50)),
        "p95": float(np.percentile(values, 95)),
        "mean": float(values.mean()),
    }
    report["by_device"] = _breakdown(levels["interactive"], image_ids, records, "device")
    return report


def _breakdown(matched: MatchedSet, image_ids: list[int], records: dict, field: str) -> dict:
    by: dict[str, list[int]] = {}
    for index, image_id in enumerate(image_ids):
        by.setdefault(getattr(records[image_id], field), []).append(index)
    return {
        value: {"images": len(indices), "mAP50": matched.summary(indices)["mAP50"]}
        for value, indices in sorted(by.items())
    }
