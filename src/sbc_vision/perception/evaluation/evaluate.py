"""Évalue un détecteur sur un sous-ensemble figé d'un corpus.

    python -m sbc_vision.perception.evaluation.evaluate \
        --corpus <corpus> --split val --count 500 \
        --near-duplicate-max 18 --data-root <extrait> \
        --detector opencv:models/opencv-gbdt.pkl --out reports/opencv/val

Sur la validation, le seuil du point de fonctionnement est celui du meilleur F1 ; sur un test,
on passe `--threshold-from` le rapport de validation, pour ne jamais régler sur le test.
"""

import argparse
import json
from pathlib import Path

from sbc_vision.perception.datasets.records import read_corpus
from sbc_vision.perception.datasets.subsets import evaluation_subset
from sbc_vision.perception.detector import load_detector
from sbc_vision.perception.elements import read_threshold
from sbc_vision.perception.evaluation.metrics import LEVELS
from sbc_vision.perception.evaluation.runner import (
    evaluate,
    ground_truth,
    load_predictions,
    run_detector,
)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--corpus", type=Path, required=True)
    parser.add_argument("--split", required=True)
    parser.add_argument("--data-root", type=Path, required=True)
    parser.add_argument("--count", type=int, help="nombre de sites ou de pages ; tous sinon")
    parser.add_argument(
        "--one-per",
        choices=("domain", "group"),
        default="domain",
        help="une capture par site (WebUI) ou par page (test vérifié : toutes ses captures)",
    )
    parser.add_argument("--seed", type=int, default=0)
    parser.add_argument("--detector", required=True, help="opencv:<modèle.pkl> ou yolo:<.onnx>")
    threshold = parser.add_mutually_exclusive_group()
    threshold.add_argument("--threshold", type=float)
    threshold.add_argument(
        "--threshold-from", type=Path, help="rapport de validation dont reprendre le seuil"
    )
    parser.add_argument("--bootstrap", type=int, default=500)
    parser.add_argument(
        "--bootstrap-by",
        choices=("domain", "group"),
        default="domain",
        help="unité rééchantillonnée : le site, ou la page pour un test tiré d'un seul site",
    )
    parser.add_argument(
        "--near-duplicate-max",
        type=int,
        help="écarter les pages à cette distance (bits) ou moins d'une page d'entraînement",
    )
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()

    corpus = read_corpus(args.corpus, args.split)
    subset = evaluation_subset(
        args.corpus, args.split, args.count, args.seed, args.near_duplicate_max, args.one_per
    )
    detector = load_detector(args.detector)
    predictions_path = args.out / "predictions.jsonl"
    run_detector(detector, subset.records, args.data_root, predictions_path)
    predictions, latencies = load_predictions(predictions_path)
    threshold = read_threshold(args.threshold_from) if args.threshold_from else args.threshold
    report = evaluate(
        subset.records,
        ground_truth(corpus),
        predictions,
        latencies,
        threshold,
        args.bootstrap,
        args.bootstrap_by,
    )
    report["detector"] = {"name": detector.name, "spec": args.detector}
    report["subset"] = {
        "split": args.split,
        "count": len(subset.records),
        "seed": args.seed,
        "one_per": args.one_per,
        "bootstrap_by": args.bootstrap_by,
        "near_duplicate_max": args.near_duplicate_max,
        "pages_excluded_near_duplicates": subset.pages_excluded,
    }
    (args.out / "report.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(
        json.dumps(
            {
                "images": report["images"],
                "threshold": round(report["threshold"], 3),
                **{
                    level: {
                        "mAP50": round(report[level]["mAP50"], 3),
                        "ci95": [round(v, 3) for v in report[level]["mAP50_ci95"]],
                        "mAP50_95": round(report[level]["mAP50_95"], 3),
                        "F1": round(report[level]["operating_point"]["_all"]["f1"], 3),
                    }
                    for level in LEVELS
                },
                "latency_ms": {k: round(v, 1) for k, v in report["latency_ms"].items()},
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
