"""Faire tourner un détecteur sur un split, puis mesurer ses prédictions.

Toutes les approches passent par la même interface (`Detector`) et le même rapport : seules
leurs prédictions changent. Le seuil de score du point de fonctionnement est choisi sur la
validation (meilleur F1) et réutilisé tel quel sur les tests.
"""

import json
import time
from collections.abc import Sequence
from pathlib import Path

import numpy as np
from PIL import Image

from sbc_vision.perception.datasets.records import Corpus, ImageRecord
from sbc_vision.perception.detector import Detector
from sbc_vision.perception.evaluation.metrics import (
    ImageBoxes,
    MatchedSet,
    bootstrap_interval,
    confusion_matrix,
    match_levels,
)
from sbc_vision.perception.ontology import DETECTOR_CLASSES


def ground_truth(corpus: Corpus) -> dict[int, ImageBoxes]:
    """Vérité de chaque image du corpus, au format de la mesure."""
    return {
        image_id: ImageBoxes([box.kind.value for box in boxes], [box.box for box in boxes])
        for image_id, boxes in corpus.boxes.items()
    }


def run_detector(
    detector: Detector, records: Sequence[ImageRecord], data_root: Path, out_path: Path
) -> None:
    """Écrit une ligne JSON par image : détections et latence de `detect` (ms)."""
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with out_path.open("w", encoding="utf-8") as handle:
        for record in records:
            with Image.open(data_root / record.file_name) as source:
                pixels = np.asarray(source.convert("RGB"))
            started = time.perf_counter()
            detections = detector.detect(pixels)
            latency_ms = (time.perf_counter() - started) * 1000
            handle.write(
                json.dumps(
                    {
                        "image_id": record.image_id,
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


def predicted_records(corpus: Corpus, predictions: dict[int, ImageBoxes]) -> list[ImageRecord]:
    """Captures du corpus couvertes par les prédictions, qui ne doivent viser qu'elles."""
    records = [image for image in corpus.images if image.image_id in predictions]
    if len(records) != len(predictions):
        raise ValueError("des prédictions visent des images absentes du corpus")
    return records


def best_f1_threshold(matched: MatchedSet) -> float:
    scores = [part.scores for image in matched.images for part in image.labels.values()]
    candidates = np.unique(np.concatenate(scores)) if scores else np.zeros(0)
    if not len(candidates):
        raise ValueError("aucune prédiction : pas de seuil à choisir")
    best, best_f1 = None, -1.0
    for threshold in np.quantile(candidates, np.linspace(0, 1, 201)):
        f1 = matched.operating_point(float(threshold))["_all"]["f1"]
        if f1 > best_f1:
            best, best_f1 = float(threshold), f1
    return best


def evaluate(
    records: Sequence[ImageRecord],
    truth: dict[int, ImageBoxes],
    predictions: dict[int, ImageBoxes],
    latencies: dict[int, float],
    threshold: float | None,
    bootstrap_samples: int,
    bootstrap_by: str,
) -> dict:
    """Rapport complet. Sans seuil donné, celui du meilleur F1 (validation). Le bootstrap
    rééchantillonne des sites (`domain`) ou, pour un test tiré d'un seul site, des pages
    (`group`)."""
    image_ids = [record.image_id for record in records]
    if set(image_ids) != set(predictions):
        raise ValueError("prédictions et captures évaluées désaccordées")
    gts = [truth[i] for i in image_ids]
    preds = [predictions[i] for i in image_ids]
    groups = [getattr(record, bootstrap_by) for record in records]
    levels = match_levels(gts, preds)
    source = "argument" if threshold is not None else "best F1 on this split"
    if threshold is None:
        threshold = best_f1_threshold(levels["kind"])
    report: dict = {"images": len(image_ids), "threshold": threshold, "threshold_source": source}
    for level, matched in levels.items():
        low, high = bootstrap_interval(matched.map50, len(image_ids), groups, bootstrap_samples)
        report[level] = {
            **matched.summary(),
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
    by_device: dict[str, list[int]] = {}
    for index, record in enumerate(records):
        by_device.setdefault(record.device, []).append(index)
    report["by_device"] = {
        device: {"images": len(indices), "mAP50": levels["interactive"].map50(indices)}
        for device, indices in sorted(by_device.items())
    }
    return report
