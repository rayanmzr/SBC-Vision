"""D-RISE (Petsiuk et al., CVPR 2021) : ce qui, dans l'image, fait exister une détection.

    python -m sbc_vision.perception.explain.drise --detector yolo:<modèle.onnx> \
        --image <capture> --threshold 0.30 --out reports/explain/<nom>

On cache l'image au hasard (une grille grossière agrandie et décalée, comme RISE), on relance
le détecteur, et on pondère chaque masque par la ressemblance de ce qu'il détecte encore avec la
détection à expliquer : IoU des boîtes × score, pour une détection de même classe. La carte de
chaleur est la moyenne pondérée des masques : une zone chaude est une zone dont la présence fait
exister la détection. Méthode boîte noire, valable pour toutes les approches (`Detector`). Nos
détecteurs ne rendent que le score de leur classe : la similarité de D-RISE d'origine, qui
compare des vecteurs de probabilités, se réduit à ce produit.
"""

import argparse
import json
from collections.abc import Sequence
from pathlib import Path

import cv2
import numpy as np
from PIL import Image

from sbc_vision.perception.boxes import iou_matrix
from sbc_vision.perception.detector import Detection, Detector, load_detector
from sbc_vision.perception.elements import read_threshold

GRID = 32  # cellules par côté : un élément d'interface fait quelques dizaines de pixels
KEEP = 0.5  # part des cellules visibles dans un masque
FILL = 127  # gris des zones cachées (un noir créerait des contours qui n'existent pas)
SEED = 0


def random_masks(height: int, width: int, count: int, seed: int):
    """Masques souples (H, W) dans [0, 1] : grille aléatoire agrandie, décalée au hasard."""
    rng = np.random.default_rng(seed)
    cell_h, cell_w = -(-height // GRID), -(-width // GRID)
    for _ in range(count):
        grid = (rng.random((GRID + 1, GRID + 1)) < KEEP).astype(np.float32)
        large = cv2.resize(
            grid, ((GRID + 1) * cell_w, (GRID + 1) * cell_h), interpolation=cv2.INTER_LINEAR
        )
        dy, dx = int(rng.integers(0, cell_h)), int(rng.integers(0, cell_w))
        yield large[dy : dy + height, dx : dx + width]


def explain(
    detector: Detector, image: np.ndarray, targets: Sequence[Detection], count: int
) -> np.ndarray:
    """Cartes de chaleur (n_cibles, H, W), une par détection à expliquer, mêmes masques."""
    height, width = image.shape[:2]
    target_boxes = np.array([box for _, box, _ in targets], dtype=np.float64).reshape(-1, 4)
    saliency = np.zeros((len(targets), height, width), dtype=np.float64)
    for mask in random_masks(height, width, count, SEED):
        masked = image * mask[..., None] + FILL * (1 - mask[..., None])
        detections = detector.detect(masked.astype(np.uint8))
        if not detections:
            continue
        boxes = np.array([box for _, box, _ in detections], dtype=np.float64)
        scores = np.array([score for _, _, score in detections])
        same = np.array([[t[0] == d[0] for d in detections] for t in targets])
        weights = (iou_matrix(target_boxes, boxes) * scores[None, :] * same).max(axis=1)
        saliency += weights[:, None, None] * mask[None]
    return saliency / count


def evidence(saliency: np.ndarray) -> np.ndarray:
    """Ce qui aide la détection : la chaleur au-dessus de sa moyenne (le reste est du bruit)."""
    return np.clip(saliency - saliency.mean(), 0, None)


def concentration(saliency: np.ndarray, box: tuple[float, ...]) -> float:
    """Part de l'évidence dans la boîte, rapportée à la part de l'image qu'occupe la boîte :
    1 si la boîte n'attire pas plus qu'ailleurs, 10 si elle attire dix fois plus."""
    heat = evidence(saliency)
    x1, y1, x2, y2 = (int(round(v)) for v in box)
    share_of_image = (x2 - x1) * (y2 - y1) / heat.size
    return float(heat[y1:y2, x1:x2].sum() / heat.sum() / share_of_image)


def overlay(image: np.ndarray, saliency: np.ndarray, box: tuple[float, ...]) -> np.ndarray:
    """Image RGB : évidence en couleur, d'autant plus opaque qu'elle est forte ; boîte en blanc."""
    heat = evidence(saliency)
    heat = np.clip(heat / np.percentile(heat, 99.5), 0, 1)
    colored = cv2.applyColorMap((heat * 255).astype(np.uint8), cv2.COLORMAP_TURBO)[..., ::-1]
    alpha = 0.75 * heat[..., None]
    blended = ((1 - alpha) * image + alpha * colored).astype(np.uint8)
    x1, y1, x2, y2 = (int(round(v)) for v in box)
    cv2.rectangle(blended, (x1, y1), (x2, y2), (255, 255, 255), 3)
    cv2.rectangle(blended, (x1 - 2, y1 - 2), (x2 + 2, y2 + 2), (0, 0, 0), 1)
    return blended


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--detector", required=True, help="opencv:<modèle.pkl> ou yolo:<.onnx>")
    parser.add_argument("--image", type=Path, required=True)
    threshold = parser.add_mutually_exclusive_group(required=True)
    threshold.add_argument("--threshold", type=float)
    threshold.add_argument("--threshold-from", type=Path, help="rapport de validation")
    parser.add_argument("--masks", type=int, default=1000)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()

    detector = load_detector(args.detector)
    with Image.open(args.image) as source:
        image = np.asarray(source.convert("RGB"))
    cut = read_threshold(args.threshold_from) if args.threshold_from else args.threshold
    targets = [d for d in detector.detect(image) if d[2] >= cut]
    saliency = explain(detector, image, targets, args.masks)
    args.out.mkdir(parents=True, exist_ok=True)
    np.savez_compressed(args.out / "saliency.npz", saliency=saliency.astype(np.float32))
    summary = []
    for index, (kind, box, score) in enumerate(targets):
        Image.fromarray(overlay(image, saliency[index], box)).save(args.out / f"{index:02d}.png")
        lift = concentration(saliency[index], box)
        summary.append(
            {"index": index, "kind": kind, "box": box, "score": score, "concentration": lift}
        )
    run = {"detector": args.detector, "image": str(args.image), "masks": args.masks}
    (args.out / "explain.json").write_text(json.dumps({**run, "targets": summary}, indent=2))
    print(json.dumps({"targets": len(targets)}))


if __name__ == "__main__":
    main()
