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

from sbc_vision.perception.datasets.records import read_corpus
from sbc_vision.perception.evaluation.metrics import match_levels, paired_bootstrap
from sbc_vision.perception.evaluation.runner import (
    ground_truth,
    load_predictions,
    predicted_records,
)


def compare(
    corpus_dir: Path,
    split: str,
    report_a: Path,
    report_b: Path,
    bootstrap_samples: int,
    bootstrap_by: str,
) -> dict:
    corpus = read_corpus(corpus_dir, split)
    predictions_a, _ = load_predictions(report_a / "predictions.jsonl")
    predictions_b, _ = load_predictions(report_b / "predictions.jsonl")
    if predictions_a.keys() != predictions_b.keys():
        raise ValueError("les deux évaluations ne portent pas sur les mêmes captures")
    records = predicted_records(corpus, predictions_a)
    truth = ground_truth(corpus)
    gts = [truth[record.image_id] for record in records]
    groups = [getattr(record, bootstrap_by) for record in records]
    levels_a = match_levels(gts, [predictions_a[record.image_id] for record in records])
    levels_b = match_levels(gts, [predictions_b[record.image_id] for record in records])
    names = [json.loads((r / "report.json").read_text())["detector"] for r in (report_a, report_b)]
    result: dict = {"split": split, "images": len(records), "a": names[0], "b": names[1]}
    for level, matched_a in levels_a.items():
        matched_b = levels_b[level]
        result[level] = {
            "mAP50_a": matched_a.map50(range(len(records))),
            "mAP50_b": matched_b.map50(range(len(records))),
            **paired_bootstrap(
                matched_a.map50, matched_b.map50, len(records), groups, bootstrap_samples
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
