"""Approche B à l'inférence : modèle YOLO exporté en ONNX, exécuté par ONNX Runtime sur CPU.

Prétraitement d'Ultralytics : redimensionnement sans déformation (letterbox) vers un carré,
bandes grises (114), RGB normalisé dans [0, 1]. Sortie de notre export : (1, 4 + classes, N),
soit cx, cy, w, h puis un score par classe ; une suppression des non-maxima par classe retire les
doublons. Les boîtes reviennent dans les pixels de la capture d'origine.
"""

from pathlib import Path

import cv2
import numpy as np

from sbc_vision.perception.boxes import clip, to_detections
from sbc_vision.perception.detector import Detection
from sbc_vision.perception.ontology import DETECTOR_CLASSES


def letterbox(image: np.ndarray, size: int) -> tuple[np.ndarray, float, tuple[float, float]]:
    height, width = image.shape[:2]
    scale = min(size / height, size / width)
    new_w, new_h = round(width * scale), round(height * scale)
    resized = cv2.resize(image, (new_w, new_h), interpolation=cv2.INTER_LINEAR)
    pad_x, pad_y = (size - new_w) / 2, (size - new_h) / 2
    top, left = round(pad_y - 0.1), round(pad_x - 0.1)
    canvas = np.full((size, size, 3), 114, dtype=np.uint8)
    canvas[top : top + new_h, left : left + new_w] = resized
    return canvas, scale, (left, top)


# Point de fonctionnement de l'inférence : candidats gardés pour la mesure (le seuil final se
# choisit sur la validation), recouvrement au-delà duquel deux boîtes de même classe sont un
# doublon, plafond par image comme COCO, fils de calcul sur processeur.
MIN_SCORE = 0.01
NMS_IOU = 0.6
MAX_DETECTIONS = 300
THREADS = 4


class YoloOnnxDetector:
    def __init__(self, path: Path):
        import onnxruntime

        options = onnxruntime.SessionOptions()
        options.intra_op_num_threads = THREADS
        self.session = onnxruntime.InferenceSession(
            str(path), options, providers=["CPUExecutionProvider"]
        )
        input_meta, output_meta = self.session.get_inputs()[0], self.session.get_outputs()[0]
        if output_meta.shape[:2] != [1, 4 + len(DETECTOR_CLASSES)]:
            raise ValueError(
                f"sortie ONNX {output_meta.shape} : (1, {4 + len(DETECTOR_CLASSES)}, N) attendue"
            )
        self.input_name = input_meta.name
        self.size = int(input_meta.shape[2])
        self.name = f"yolo-onnx:{Path(path).stem}"

    def detect(self, image: np.ndarray) -> list[Detection]:
        canvas, scale, (left, top) = letterbox(image, self.size)
        blob = canvas.transpose(2, 0, 1)[None].astype(np.float32) / 255.0
        predictions = self.session.run(None, {self.input_name: blob})[0][0].T  # (N, 4 + classes)
        centers, class_scores = predictions[:, :4], predictions[:, 4:]
        classes = class_scores.argmax(axis=1)
        scores = class_scores[np.arange(len(classes)), classes]
        keep = scores >= MIN_SCORE
        centers, scores, classes = centers[keep], scores[keep], classes[keep]
        boxes = np.concatenate(
            [centers[:, :2] - centers[:, 2:] / 2, centers[:, :2] + centers[:, 2:] / 2], axis=1
        )
        height, width = image.shape[:2]
        boxes = clip((boxes - np.array([left, top, left, top])) / scale, width, height)
        valid = (boxes[:, 2] > boxes[:, 0]) & (boxes[:, 3] > boxes[:, 1])
        kinds = [DETECTOR_CLASSES[c].value for c in classes[valid]]
        return to_detections(boxes[valid], kinds, scores[valid], NMS_IOU, MAX_DETECTIONS)
