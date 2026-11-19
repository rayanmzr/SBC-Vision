"""Contrôle de cohérence entre étiquettes issues du DOM et pixels de la capture.

Les boîtes viennent de l'arbre de la page, la capture d'un autre instant : une page pas encore
affichée, ou masquée, donne des boîtes posées sur un fond uniforme. Ces boîtes sont écartées, et
une page où elles sont nombreuses est exclue entière, car ses autres boîtes sont suspectes aussi.
"""

from dataclasses import dataclass

import numpy as np


@dataclass(frozen=True)
class QualityRules:
    min_box_std: float = 3.0  # écart type des niveaux de gris sous la boîte (0-255)
    max_uniform_share: float = 0.3
    min_uniform_count: int = 3


DEFAULT_QUALITY_RULES = QualityRules()


@dataclass(frozen=True)
class PageQuality:
    uniform: list[bool]
    excluded: bool

    @property
    def uniform_count(self) -> int:
        return sum(self.uniform)


def box_std(gray: np.ndarray, box: tuple[float, float, float, float]) -> float:
    x1, y1, x2, y2 = box
    crop = gray[int(y1) : int(np.ceil(y2)), int(x1) : int(np.ceil(x2))]
    return float(crop.std()) if crop.size else 0.0


def assess_page(
    gray: np.ndarray, boxes: list[tuple[float, float, float, float]], rules: QualityRules
) -> PageQuality:
    uniform = [box_std(gray, box) < rules.min_box_std for box in boxes]
    count = sum(uniform)
    excluded = bool(
        boxes and count >= rules.min_uniform_count and count / len(boxes) >= rules.max_uniform_share
    )
    return PageQuality(uniform=uniform, excluded=excluded)
