"""Compare deux détecteurs évalués sur le même sous-ensemble : écart apparié de mAP@0,5.

    python -m sbc_vision.perception.evaluation.compare --corpus <corpus> --split val \
        --a reports/yolo/val --b reports/opencv/val --out reports/yolo-vs-opencv-val.json

Les deux dossiers sont des sorties de `evaluate` sur les mêmes captures. Chaque tirage du
bootstrap reprend les mêmes sites pour les deux détecteurs : l'écart tient compte de ce que les
sites ont en commun (une page difficile l'est pour les deux), d'où un intervalle plus serré que
la comparaison de deux intervalles séparés.
"""

import argparse
import json
from pathlib import Path

from sbc_vision.perception.datasets.records import read_manifest
from sbc_vision.perception.evaluation.metrics import LEVELS, match_dataset, paired_bootstrap
from sbc_vision.perception.evaluation.runner import load_ground_truth, load_predictions


def compare(
    corpus: Path,
    split: str,
    report_a: Path,
    report_b: Path,
    bootstrap_samples: int,
    bootstrap_by: str = "domain",
) -> dict:
    truth = load_ground_truth(corpus / f"{split}.coco.json")
    units = {
        r.image_id: getattr(r, bootstrap_by)
        for r in read_manifest(corpus / f"{split}.manifest.jsonl")
    }
    predictions_a, _ = load_predictions(report_a / "predictions.jsonl")
    predictions_b, _ = load_predictions(report_b / "predictions.jsonl")
    if predictions_a.keys() != predictions_b.keys():
        raise ValueError("les deux évaluations ne portent pas sur les mêmes captures")
    image_ids = [image["id"] for image in truth.images if image["id"] in predictions_a]
    gts = [truth.boxes[i] for i in image_ids]
    groups = [units[i] for i in image_ids]
    names = [json.loads((r / "report.json").read_text())["detector"] for r in (report_a, report_b)]
    result: dict = {"split": split, "images": len(image_ids), "a": names[0], "b": names[1]}
    for level in LEVELS:
        matched_a = match_dataset(gts, [predictions_a[i] for i in image_ids], level)
        matched_b = match_dataset(gts, [predictions_b[i] for i in image_ids], level)
        result[level] = {
            "mAP50_a": matched_a.summary()["mAP50"],
            "mAP50_b": matched_b.summary()["mAP50"],
            **paired_bootstrap(
                lambda idx, m=matched_a: m.summary(idx)["mAP50"],
                lambda idx, m=matched_b: m.summary(idx)["mAP50"],
                len(image_ids),
                groups,
                samples=bootstrap_samples,
            ),
        }
    return result


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--corpus", type=Path, required=True)
    parser.add_argument("--split", required=True)
    parser.add_argument("--a", type=Path, required=True, help="dossier d'évaluation du détecteur A")
    parser.add_argument("--b", type=Path, required=True, help="dossier d'évaluation du détecteur B")
    parser.add_argument("--bootstrap", type=int, default=500)
    parser.add_argument("--bootstrap-by", choices=("domain", "group"), default="domain")
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    result = compare(args.corpus, args.split, args.a, args.b, args.bootstrap, args.bootstrap_by)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(result, indent=2), encoding="utf-8")
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
