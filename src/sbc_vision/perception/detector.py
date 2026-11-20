"""Interface commune des détecteurs : toutes les approches rendent la même chose."""

from typing import Protocol

import numpy as np

# Classe (`ElementKind.value`), boîte x1, y1, x2, y2 en pixels de l'image, score dans [0, 1].
Detection = tuple[str, tuple[float, float, float, float], float]


class Detector(Protocol):
    name: str

    def detect(self, image: np.ndarray) -> list[Detection]:
        """Image RGB (H, W, 3) en uint8 ; boîtes x1, y1, x2, y2 dans ses pixels."""
        ...
