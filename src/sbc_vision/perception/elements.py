"""Sortie d'un détecteur au format du contrat de perception (`DetectedElement`).

Les détections gardées sont celles dont le score atteint le seuil du point de fonctionnement,
choisi sur la validation (`threshold` du rapport d'évaluation). Les boîtes passent en pixels
entiers, arrondies vers l'extérieur ; l'action vient de la classe (`ontology.ACTIONS`). Le texte
est laissé vide : il vient de la lecture (OCR).
"""

import json
import math
from collections.abc import Sequence
from pathlib import Path

from sbc_vision.contracts.perception import BoundingBox, DetectedElement, ElementKind
from sbc_vision.perception.detector import Detection
from sbc_vision.perception.ontology import ACTIONS


def read_threshold(report: Path) -> float:
    """Seuil du point de fonctionnement, choisi sur la validation, d'un rapport d'évaluation."""
    return json.loads(report.read_text(encoding="utf-8"))["threshold"]


def to_elements(detections: Sequence[Detection], min_score: float) -> list[DetectedElement]:
    """Éléments du contrat, par score décroissant, identifiés `e0`, `e1`…"""
    kept = sorted((d for d in detections if d[2] >= min_score), key=lambda d: -d[2])
    elements = []
    for index, (kind, (x1, y1, x2, y2), score) in enumerate(kept):
        left, top = math.floor(x1), math.floor(y1)
        elements.append(
            DetectedElement(
                id=f"e{index}",
                kind=ElementKind(kind),
                bbox=BoundingBox(
                    x=left, y=top, width=math.ceil(x2) - left, height=math.ceil(y2) - top
                ),
                confidence=score,
                actions=list(ACTIONS[ElementKind(kind)]),
            )
        )
    return elements
