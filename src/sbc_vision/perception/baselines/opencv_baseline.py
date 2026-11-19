"""Approche A : propositions OpenCV et classifieur classique sur des caractéristiques lisibles.

1. Propositions : contours (blocs, cadres, champs) et regroupement morphologique des lettres
   (liens, textes cliquables). Aucune donnée apprise.
2. Caractéristiques de chaque proposition, calculées en temps constant par images intégrales :
   géométrie, contraste, cadre, remplissage, densité de texte, emboîtement.
3. Classifieur (gradient boosting) : fond ou l'une des classes du détecteur. Le score de la
   classe retenue sert de confiance ; une suppression des non-maxima par classe retire les doublons.

Le rappel des propositions borne celui de l'approche : il est mesuré séparément.
"""

import pickle
from dataclasses import dataclass, field
from pathlib import Path

import cv2
import numpy as np

from sbc_vision.perception.boxes import nms_per_class

BACKGROUND = "background"

FEATURE_NAMES = (
    "width_rel",
    "height_rel",
    "log_aspect",
    "log_area",
    "center_x",
    "center_y",
    "gray_mean",
    "gray_std",
    "edge_density",
    "text_density",
    "saturation_mean",
    "inner_ring_edges",
    "outer_ring_edges",
    "fill_contrast",
    "outer_ring_std",
    "children",
    "parents",
    "from_contours",
    "from_text",
)


@dataclass(frozen=True)
class ProposalParams:
    canny_low: int = 40
    canny_high: int = 120
    soft_canny_low: int = 15  # boutons peu contrastés (gris clair sur blanc)
    soft_canny_high: int = 45
    gradient_threshold: int = 30
    word_gap: int = 7  # pixels comblés entre deux lettres d'un même mot
    phrase_gap: int = 15
    # Marges ajoutées autour d'un texte : la zone cliquable d'un lien ou d'un bouton déborde
    # du texte (padding), invisible quand le fond est uniforme.
    text_paddings: tuple[tuple[int, int], ...] = ((0, 0), (4, 3), (10, 8), (16, 14))
    min_side: int = 6
    max_area_fraction: float = 0.6
    max_proposals: int = 6000


DEFAULT_PARAMS = ProposalParams()


@dataclass
class Maps:
    """Images intégrales des cartes utilisées par les caractéristiques."""

    height: int
    width: int
    integrals: dict[str, np.ndarray] = field(default_factory=dict)

    def mean(self, name: str, boxes: np.ndarray) -> np.ndarray:
        integral = self.integrals[name]
        x1, y1, x2, y2 = (boxes[:, i] for i in range(4))
        total = integral[y2, x2] - integral[y1, x2] - integral[y2, x1] + integral[y1, x1]
        area = np.maximum((x2 - x1) * (y2 - y1), 1)
        return total / area

    def ring_mean(self, name: str, outer: np.ndarray, inner: np.ndarray) -> np.ndarray:
        integral = self.integrals[name]

        def total(b):
            return (
                integral[b[:, 3], b[:, 2]]
                - integral[b[:, 1], b[:, 2]]
                - integral[b[:, 3], b[:, 0]]
                + integral[b[:, 1], b[:, 0]]
            )

        area_outer = (outer[:, 2] - outer[:, 0]) * (outer[:, 3] - outer[:, 1])
        area_inner = (inner[:, 2] - inner[:, 0]) * (inner[:, 3] - inner[:, 1])
        return (total(outer) - total(inner)) / np.maximum(area_outer - area_inner, 1)


def build_maps(rgb: np.ndarray, params: ProposalParams) -> tuple[Maps, np.ndarray, np.ndarray]:
    gray = cv2.cvtColor(rgb, cv2.COLOR_RGB2GRAY)
    edges = cv2.Canny(gray, params.canny_low, params.canny_high)
    gradient = cv2.morphologyEx(
        gray, cv2.MORPH_GRADIENT, cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (3, 3))
    )
    text = (gradient > params.gradient_threshold).astype(np.uint8)
    saturation = cv2.cvtColor(rgb, cv2.COLOR_RGB2HSV)[:, :, 1]
    maps = Maps(height=gray.shape[0], width=gray.shape[1])
    gray_f = gray.astype(np.float64)
    maps.integrals["gray"] = cv2.integral(gray_f)
    maps.integrals["gray2"] = cv2.integral(gray_f * gray_f)
    maps.integrals["edges"] = cv2.integral((edges > 0).astype(np.float64))
    maps.integrals["text"] = cv2.integral(text.astype(np.float64))
    maps.integrals["saturation"] = cv2.integral(saturation.astype(np.float64))
    for index, channel in enumerate("rgb"):
        maps.integrals[channel] = cv2.integral(rgb[:, :, index].astype(np.float64))
    return maps, edges, text


def _rects(mask: np.ndarray) -> np.ndarray:
    contours, _ = cv2.findContours(mask, cv2.RETR_LIST, cv2.CHAIN_APPROX_SIMPLE)
    if not contours:
        return np.zeros((0, 4), dtype=np.int64)
    rects = np.array([cv2.boundingRect(contour) for contour in contours], dtype=np.int64)
    rects[:, 2] += rects[:, 0]
    rects[:, 3] += rects[:, 1]
    return rects


def propose(
    rgb: np.ndarray, params: ProposalParams = DEFAULT_PARAMS
) -> tuple[np.ndarray, np.ndarray, Maps]:
    """Boîtes candidates (n, 4) en pixels entiers, leur origine (0 contours, 1 texte), cartes."""
    maps, edges, text = build_maps(rgb, params)
    gray = cv2.cvtColor(rgb, cv2.COLOR_RGB2GRAY)
    soft = cv2.Canny(gray, params.soft_canny_low, params.soft_canny_high)
    kernel = np.ones((3, 3), np.uint8)
    from_contours = np.vstack([_rects(cv2.dilate(edges, kernel)), _rects(cv2.dilate(soft, kernel))])
    words = cv2.morphologyEx(text, cv2.MORPH_CLOSE, np.ones((1, params.word_gap), np.uint8))
    phrases = cv2.morphologyEx(text, cv2.MORPH_CLOSE, np.ones((3, params.phrase_gap), np.uint8))
    tight = np.vstack([_rects(words), _rects(phrases)])
    from_text = np.vstack([tight + np.array([-dx, -dy, dx, dy]) for dx, dy in params.text_paddings])
    from_text[:, [0, 2]] = np.clip(from_text[:, [0, 2]], 0, maps.width)
    from_text[:, [1, 3]] = np.clip(from_text[:, [1, 3]], 0, maps.height)
    boxes = np.vstack([from_contours, from_text])
    source = np.concatenate([np.zeros(len(from_contours)), np.ones(len(from_text))])

    w, h = boxes[:, 2] - boxes[:, 0], boxes[:, 3] - boxes[:, 1]
    keep = (
        (w >= params.min_side)
        & (h >= params.min_side)
        & (w * h <= params.max_area_fraction * maps.width * maps.height)
    )
    boxes, source = boxes[keep], source[keep]
    # Doublons exacts entre les deux sources : garder la première occurrence.
    _, unique = np.unique(boxes, axis=0, return_index=True)
    unique = np.sort(unique)
    boxes, source = boxes[unique], source[unique]
    if len(boxes) > params.max_proposals:
        # Garder les plus grandes : les éléments interactifs sont rarement minuscules.
        area = (boxes[:, 2] - boxes[:, 0]) * (boxes[:, 3] - boxes[:, 1])
        order = np.argsort(-area)[: params.max_proposals]
        boxes, source = boxes[order], source[order]
    return boxes, source, maps


def _nesting(boxes: np.ndarray, chunk: int = 512) -> tuple[np.ndarray, np.ndarray]:
    """Nombre de propositions contenues dans chaque boîte, et qui la contiennent."""
    n = len(boxes)
    children = np.zeros(n)
    parents = np.zeros(n)
    for start in range(0, n, chunk):
        part = boxes[start : start + chunk]
        inside = (
            (boxes[None, :, 0] >= part[:, None, 0])
            & (boxes[None, :, 1] >= part[:, None, 1])
            & (boxes[None, :, 2] <= part[:, None, 2])
            & (boxes[None, :, 3] <= part[:, None, 3])
        )
        inside[np.arange(len(part)), np.arange(start, start + len(part))] = False
        children[start : start + chunk] = inside.sum(axis=1)
        parents += inside.sum(axis=0)
    return children, parents


def features(boxes: np.ndarray, source: np.ndarray, maps: Maps) -> np.ndarray:
    W, H = maps.width, maps.height
    w = (boxes[:, 2] - boxes[:, 0]).astype(np.float64)
    h = (boxes[:, 3] - boxes[:, 1]).astype(np.float64)

    def clip(b):
        b = b.copy()
        b[:, [0, 2]] = np.clip(b[:, [0, 2]], 0, W)
        b[:, [1, 3]] = np.clip(b[:, [1, 3]], 0, H)
        return b

    inner = boxes.copy()
    shrink = np.minimum(2, np.minimum(w, h) // 4).astype(np.int64)
    inner[:, 0] += shrink
    inner[:, 1] += shrink
    inner[:, 2] -= shrink
    inner[:, 3] -= shrink
    outer = clip(boxes + np.array([-3, -3, 3, 3]))

    gray_mean = maps.mean("gray", boxes)
    gray_std = np.sqrt(np.maximum(maps.mean("gray2", boxes) - gray_mean**2, 0))
    inside_rgb = np.stack([maps.mean(c, boxes) for c in "rgb"], axis=1)
    ring_rgb = np.stack([maps.ring_mean(c, outer, boxes) for c in "rgb"], axis=1)
    ring_gray = maps.ring_mean("gray", outer, boxes)
    ring_gray2 = maps.ring_mean("gray2", outer, boxes)
    children, parents = _nesting(boxes)
    columns = [
        w / W,
        h / H,
        np.log(w / h),
        np.log(w * h),
        (boxes[:, 0] + boxes[:, 2]) / (2 * W),
        (boxes[:, 1] + boxes[:, 3]) / (2 * H),
        gray_mean,
        gray_std,
        maps.mean("edges", boxes),
        maps.mean("text", boxes),
        maps.mean("saturation", boxes),
        maps.ring_mean("edges", boxes, inner),
        maps.ring_mean("edges", outer, boxes),
        np.linalg.norm(inside_rgb - ring_rgb, axis=1),
        np.sqrt(np.maximum(ring_gray2 - ring_gray**2, 0)),
        np.log1p(children),
        np.log1p(parents),
        (source == 0).astype(np.float64),
        (source == 1).astype(np.float64),
    ]
    return np.stack(columns, axis=1).astype(np.float32)


class OpenCVBaseline:
    """Détecteur de l'approche A ; `classifier` est un modèle scikit-learn entraîné."""

    def __init__(
        self,
        classifier,
        classes: tuple[str, ...],
        params: ProposalParams = DEFAULT_PARAMS,
        min_score: float = 0.05,
        nms_iou: float = 0.5,
        max_detections: int = 300,
    ):
        self.classifier = classifier
        self.classes = classes  # ordre des colonnes de predict_proba ; contient BACKGROUND
        self.params = params
        self.min_score = min_score
        self.nms_iou = nms_iou
        self.max_detections = max_detections
        self.name = "opencv-gbdt"

    def detect(self, image: np.ndarray):
        boxes, source, maps = propose(image, self.params)
        if len(boxes) == 0:
            return []
        probabilities = self.classifier.predict_proba(features(boxes, source, maps))
        background = self.classes.index(BACKGROUND)
        probabilities[:, background] = -1
        best = probabilities.argmax(axis=1)
        scores = probabilities[np.arange(len(best)), best]
        keep = scores >= self.min_score
        boxes, best, scores = boxes[keep], best[keep], scores[keep]
        kinds = [self.classes[i] for i in best]
        order = nms_per_class(boxes, kinds, scores, self.nms_iou, self.max_detections)
        return [(kinds[i], tuple(float(v) for v in boxes[i]), float(scores[i])) for i in order]

    def save(self, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("wb") as handle:
            pickle.dump(
                {"classifier": self.classifier, "classes": self.classes, "params": self.params},
                handle,
            )

    @classmethod
    def load(cls, path: Path) -> "OpenCVBaseline":
        # Fichier produit par notre propre entraînement ; ne pas charger un pickle tiers.
        with path.open("rb") as handle:
            state = pickle.load(handle)
        return cls(state["classifier"], state["classes"], state["params"])
