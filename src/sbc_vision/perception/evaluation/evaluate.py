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

from sbc_vision.perception.datasets.subsets import evaluation_subset
from sbc_vision.perception.evaluation.runner import (
    Detector,
    evaluate,
    load_ground_truth,
    load_predictions,
    run_detector,
)


def load_detector(spec: str) -> Detector:
    kind, _, path = spec.partition(":")
    if kind == "opencv":
        from sbc_vision.perception.baselines.opencv_baseline import OpenCVBaseline

        return OpenCVBaseline.load(Path(path))
    if kind == "yolo":
        from sbc_vision.perception.detectors.yolo_onnx import YoloOnnxDetector

        return YoloOnnxDetector(Path(path))
    raise ValueError(f"détecteur inconnu : {kind}")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--corpus", type=Path, required=True)
    parser.add_argument("--split", required=True)
    parser.add_argument("--data-root", type=Path, required=True)
    parser.add_argument("--count", type=int)
    parser.add_argument("--seed", type=int, default=0)
    parser.add_argument("--detector", required=True)
    parser.add_argument("--threshold", type=float)
    parser.add_argument("--threshold-from", type=Path)
    parser.add_argument("--bootstrap", type=int, default=500)
    parser.add_argument(
        "--near-duplicate-max",
        type=int,
        help="écarter les pages à cette distance (bits) ou moins d'une page d'entraînement",
    )
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()

    subset = evaluation_subset(
        args.corpus, args.split, args.count, args.seed, args.near_duplicate_max
    )
    wanted = {record.image_id for record in subset.records}
    truth = load_ground_truth(args.corpus / f"{args.split}.coco.json")
    images = [image for image in truth.images if image["id"] in wanted]

    detector = load_detector(args.detector)
    predictions_path = args.out / "predictions.jsonl"
    run_detector(detector, images, args.data_root, predictions_path)
    predictions, latencies = load_predictions(predictions_path)

    threshold = args.threshold
    if args.threshold_from:
        threshold = json.loads(args.threshold_from.read_text(encoding="utf-8"))["threshold"]
    report = evaluate(truth, predictions, latencies, subset.records, threshold, args.bootstrap)
    report["detector"] = {"name": detector.name, "spec": args.detector}
    report["subset"] = {
        "split": args.split,
        "count": len(images),
        "seed": args.seed,
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
                        "F1": round(report[level]["operating_point"]["_all"]["f1"] or 0, 3),
                    }
                    for level in ("kind", "action", "interactive")
                },
                "latency_ms": {k: round(v, 1) for k, v in report["latency_ms"].items()},
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
