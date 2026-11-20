"""Opérations sur les boîtes (x1, y1, x2, y2) : données, détecteurs et mesure."""

import cv2
import numpy as np


def iou_matrix(a: np.ndarray, b: np.ndarray) -> np.ndarray:
    """IoU de chaque boîte de `a` (n, 4) avec chaque boîte de `b` (m, 4) : matrice (n, m)."""
    if len(a) == 0 or len(b) == 0:
        return np.zeros((len(a), len(b)))
    x1 = np.maximum(a[:, None, 0], b[None, :, 0])
    y1 = np.maximum(a[:, None, 1], b[None, :, 1])
    x2 = np.minimum(a[:, None, 2], b[None, :, 2])
    y2 = np.minimum(a[:, None, 3], b[None, :, 3])
    inter = np.clip(x2 - x1, 0, None) * np.clip(y2 - y1, 0, None)
    area_a = (a[:, 2] - a[:, 0]) * (a[:, 3] - a[:, 1])
    area_b = (b[:, 2] - b[:, 0]) * (b[:, 3] - b[:, 1])
    union = area_a[:, None] + area_b[None, :] - inter
    return np.where(union > 0, inter / np.where(union > 0, union, 1), 0.0)


def nms_per_class(
    boxes: np.ndarray, kinds: list[str], scores: np.ndarray, iou: float, limit: int
) -> list[int]:
    """Indices gardés, par score décroissant, après suppression des non-maxima classe par classe."""
    kept: list[int] = []
    for kind in set(kinds):
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
