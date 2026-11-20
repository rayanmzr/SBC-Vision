"""Interface commune des détecteurs : toutes les approches rendent la même chose."""

from pathlib import Path
from typing import Protocol

import numpy as np

# Classe (`ElementKind.value`), boîte x1, y1, x2, y2 en pixels de l'image, score dans [0, 1].
Detection = tuple[str, tuple[float, float, float, float], float]


class Detector(Protocol):
    name: str

    def detect(self, image: np.ndarray) -> list[Detection]:
        """Image RGB (H, W, 3) en uint8 ; boîtes x1, y1, x2, y2 dans ses pixels."""
        ...


def load_detector(spec: str) -> Detector:
    """`opencv:<modèle.pkl>` (approche A) ou `yolo:<modèle.onnx>` (approche B)."""
    kind, _, path = spec.partition(":")
    if kind == "opencv":
        from sbc_vision.perception.baselines.opencv_baseline import OpenCVBaseline

        return OpenCVBaseline.load(Path(path))
    if kind == "yolo":
        from sbc_vision.perception.detectors.yolo_onnx import YoloOnnxDetector

        return YoloOnnxDetector(Path(path))
    raise ValueError(f"détecteur inconnu : {kind}")
