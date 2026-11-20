"""SHAP sur l'approche A : quelles caractéristiques lisibles font choisir chaque classe.

    python -m sbc_vision.perception.explain.shap_baseline --model models/opencv-gbdt.pkl \
        --corpus <corpus> --split val --count 100 --near-duplicate-max 18 \
        --data-root <extrait> --threshold-from reports/opencv/val/report.json \
        --out reports/explain/opencv-shap.json

Valeurs de Shapley exactes du gradient boosting (TreeSHAP) pour les propositions que le modèle
garde (score de sa classe au moins égal au seuil de validation) : contribution de chaque
caractéristique au score (log-odds) d'une classe. Résumé par classe : importance moyenne
(|SHAP|) sur les propositions attribuées à cette classe, et sens de l'effet sur toutes les
propositions gardées (corrélation de rang entre la valeur de la caractéristique et sa
contribution à la classe : positif, une valeur haute pousse vers la classe).
"""

import argparse
import json
from pathlib import Path

import numpy as np
import shap
from PIL import Image
from scipy.stats import spearmanr

from sbc_vision.perception.baselines.opencv_baseline import FEATURE_NAMES, OpenCVBaseline
from sbc_vision.perception.datasets.subsets import evaluation_subset
from sbc_vision.perception.elements import read_threshold


def kept_proposals(model: OpenCVBaseline, images: list[np.ndarray], threshold: float):
    """Caractéristiques et classe (indice) des propositions gardées par le modèle."""
    rows, classes = [], []
    for image in images:
        _, x, best, scores = model.classify(image)
        keep = scores >= threshold
        rows.append(x[keep])
        classes.append(best[keep])
    return np.vstack(rows), np.concatenate(classes)


def summarize(model: OpenCVBaseline, x: np.ndarray, classes: np.ndarray) -> dict:
    values = shap.TreeExplainer(model.classifier).shap_values(x)  # (n, caractéristiques, classes)
    summary = {}
    for index, name in enumerate(model.classes):
        rows = classes == index
        if not rows.any():
            continue
        features = []
        for f, feature in enumerate(FEATURE_NAMES):
            everywhere = values[:, f, index]
            varies = np.ptp(x[:, f]) > 0 and np.ptp(everywhere) > 0
            direction = spearmanr(x[:, f], everywhere).statistic if varies else 0.0
            features.append(
                {
                    "feature": feature,
                    "mean_abs_shap": float(np.abs(values[rows, f, index]).mean()),
                    "direction": float(direction),
                }
            )
        features.sort(key=lambda item: -item["mean_abs_shap"])
        summary[name] = {"proposals": int(rows.sum()), "features": features}
    return summary


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--model", type=Path, required=True)
    parser.add_argument("--corpus", type=Path, required=True)
    parser.add_argument("--split", required=True)
    parser.add_argument("--count", type=int, required=True, help="nombre de sites")
    parser.add_argument("--near-duplicate-max", type=int)
    parser.add_argument("--data-root", type=Path, required=True)
    parser.add_argument("--threshold-from", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()

    model = OpenCVBaseline.load(args.model)
    subset = evaluation_subset(
        args.corpus, args.split, args.count, 0, args.near_duplicate_max, "domain"
    )
    images = []
    for record in subset.records:
        with Image.open(args.data_root / record.file_name) as source:
            images.append(np.asarray(source.convert("RGB")))
    x, classes = kept_proposals(model, images, read_threshold(args.threshold_from))
    result = {
        "model": str(args.model),
        "split": args.split,
        "images": len(images),
        "classes": summarize(model, x, classes),
    }
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(result, indent=2), encoding="utf-8")
    print(json.dumps({name: c["proposals"] for name, c in result["classes"].items()}))


if __name__ == "__main__":
    main()
