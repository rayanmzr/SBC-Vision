"""Opérations sur les boîtes (x1, y1, x2, y2) : données, détecteurs et mesure."""

from collections.abc import Sequence

import cv2
import numpy as np

from sbc_vision.perception.detector import Detection


def area(boxes: np.ndarray) -> np.ndarray:
    return (boxes[:, 2] - boxes[:, 0]) * (boxes[:, 3] - boxes[:, 1])


def clip(boxes: np.ndarray, width: float, height: float) -> np.ndarray:
    """Boîtes rognées à l'image (copie)."""
    clipped = boxes.copy()
    clipped[:, [0, 2]] = np.clip(clipped[:, [0, 2]], 0, width)
    clipped[:, [1, 3]] = np.clip(clipped[:, [1, 3]], 0, height)
    return clipped


def intersection_matrix(a: np.ndarray, b: np.ndarray) -> np.ndarray:
    """Aire commune de chaque boîte de `a` (n, 4) avec chaque boîte de `b` (m, 4) : (n, m)."""
    x1 = np.maximum(a[:, None, 0], b[None, :, 0])
    y1 = np.maximum(a[:, None, 1], b[None, :, 1])
    x2 = np.minimum(a[:, None, 2], b[None, :, 2])
    y2 = np.minimum(a[:, None, 3], b[None, :, 3])
    return np.clip(x2 - x1, 0, None) * np.clip(y2 - y1, 0, None)


def iou_matrix(a: np.ndarray, b: np.ndarray) -> np.ndarray:
    """IoU de chaque boîte de `a` (n, 4) avec chaque boîte de `b` (m, 4) : matrice (n, m)."""
    if len(a) == 0 or len(b) == 0:
        return np.zeros((len(a), len(b)))
    inter = intersection_matrix(a, b)
    union = area(a)[:, None] + area(b)[None, :] - inter
    return np.where(union > 0, inter / np.where(union > 0, union, 1), 0.0)


def nms_per_class(
    boxes: np.ndarray, kinds: Sequence[str], scores: np.ndarray, iou: float, limit: int
) -> list[int]:
    """Indices gardés, par score décroissant, après suppression des non-maxima classe par classe."""
    kept: list[int] = []
    for kind in sorted(set(kinds)):
        indices = [i for i, k in enumerate(kinds) if k == kind]
        rects = [
            [
                float(boxes[i, 0]),
                float(boxes[i, 1]),
                float(boxes[i, 2] - boxes[i, 0]),
                float(boxes[i, 3] - boxes[i, 1]),
            ]
            for i in indices
        ]
        selected = cv2.dnn.NMSBoxes(rects, [float(scores[i]) for i in indices], 0.0, iou)
        kept.extend(indices[int(j)] for j in np.array(selected).reshape(-1))
    kept.sort(key=lambda i: -scores[i])
    return kept[:limit]


def to_detections(
    boxes: np.ndarray, kinds: Sequence[str], scores: np.ndarray, iou: float, limit: int
) -> list[Detection]:
    """Étape finale commune des détecteurs : doublons retirés, tri par score décroissant."""
    order = nms_per_class(boxes, kinds, scores, iou, limit)
    return [(kinds[i], tuple(float(v) for v in boxes[i]), float(scores[i])) for i in order]
