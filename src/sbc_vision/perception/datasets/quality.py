"""Contrôle de cohérence entre étiquettes issues du DOM et pixels de la capture.

Les boîtes viennent de l'arbre de la page, la capture d'un autre instant : une page pas encore
affichée, ou masquée, donne des boîtes posées sur un fond uniforme. Ces boîtes sont écartées, et
une page où elles sont nombreuses est exclue entière, car ses autres boîtes sont suspectes aussi.
"""

from dataclasses import dataclass

import numpy as np

MIN_BOX_STD = 3.0  # écart type des niveaux de gris sous la boîte (0-255)
# Page exclue quand au moins MIN_UNIFORM_COUNT boîtes, et MAX_UNIFORM_SHARE d'entre elles,
# sont uniformes.
MIN_UNIFORM_COUNT = 3
MAX_UNIFORM_SHARE = 0.3


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
    if not crop.size:
        raise ValueError(f"boîte vide ou hors de l'image : {box}")
    return float(crop.std())


def assess_page(gray: np.ndarray, boxes: list[tuple[float, float, float, float]]) -> PageQuality:
    uniform = [box_std(gray, box) < MIN_BOX_STD for box in boxes]
    count = sum(uniform)
    excluded = bool(
        boxes and count >= MIN_UNIFORM_COUNT and count / len(boxes) >= MAX_UNIFORM_SHARE
    )
    return PageQuality(uniform=uniform, excluded=excluded)
