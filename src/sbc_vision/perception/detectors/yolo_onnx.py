"""Approche B à l'inférence : modèle YOLO exporté en ONNX, exécuté par ONNX Runtime sur CPU.

Prétraitement d'Ultralytics : redimensionnement sans déformation (letterbox) vers un carré,
bandes grises (114), RGB normalisé dans [0, 1]. Sortie de notre export : (1, 4 + classes, N),
soit cx, cy, w, h puis un score par classe ; une suppression des non-maxima par classe retire les
doublons. Les boîtes reviennent dans les pixels de la capture d'origine.
"""

from pathlib import Path

import cv2
import numpy as np

from sbc_vision.perception.boxes import nms_per_class
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


class YoloOnnxDetector:
    def __init__(
        self,
        path: Path,
        min_score: float = 0.01,
        nms_iou: float = 0.6,
        max_detections: int = 300,
        threads: int = 4,
    ):
        import onnxruntime

        options = onnxruntime.SessionOptions()
        options.intra_op_num_threads = threads
        self.session = onnxruntime.InferenceSession(
            str(path), options, providers=["CPUExecutionProvider"]
        )
        input_meta = self.session.get_inputs()[0]
        self.input_name = input_meta.name
        self.size = int(input_meta.shape[2])
        self.min_score = min_score
        self.nms_iou = nms_iou
        self.max_detections = max_detections
        self.name = f"yolo-onnx:{Path(path).stem}"

    def detect(self, image: np.ndarray):
        canvas, scale, (left, top) = letterbox(image, self.size)
        blob = canvas.transpose(2, 0, 1)[None].astype(np.float32) / 255.0
        predictions = self.session.run(None, {self.input_name: blob})[0][0].T  # (N, 4 + classes)
        centers, class_scores = predictions[:, :4], predictions[:, 4:]
        classes = class_scores.argmax(axis=1)
        scores = class_scores[np.arange(len(classes)), classes]
        keep = scores >= self.min_score
        centers, scores, classes = centers[keep], scores[keep], classes[keep]
        boxes = np.concatenate(
            [centers[:, :2] - centers[:, 2:] / 2, centers[:, :2] + centers[:, 2:] / 2], axis=1
        )
        boxes = (boxes - np.array([left, top, left, top])) / scale
        height, width = image.shape[:2]
        boxes[:, [0, 2]] = boxes[:, [0, 2]].clip(0, width)
        boxes[:, [1, 3]] = boxes[:, [1, 3]].clip(0, height)
        valid = (boxes[:, 2] > boxes[:, 0]) & (boxes[:, 3] > boxes[:, 1])
        boxes, scores, classes = boxes[valid], scores[valid], classes[valid]
        kinds = [DETECTOR_CLASSES[c].value for c in classes]
        order = nms_per_class(boxes, kinds, scores, self.nms_iou, self.max_detections)
        return [(kinds[i], tuple(float(v) for v in boxes[i]), float(scores[i])) for i in order]
