"""Opérations sur les boîtes partagées par les détecteurs."""

import cv2
import numpy as np


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
