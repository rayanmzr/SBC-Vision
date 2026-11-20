"""Métriques communes à toutes les approches de détection.

Appariement à la manière de COCO : dans chaque image et pour chaque étiquette, les prédictions
sont prises par score décroissant et chacune prend la vérité non encore appariée de plus grand
IoU au-dessus du seuil. Ce résultat ne dépend que de l'image ; il est calculé une fois, puis
recombiné pour n'importe quel sous-ensemble ou rééchantillonnage d'images (bootstrap).

Trois niveaux d'étiquettes :
- `kind` : la classe du contrat (button, input, link…) ;
- `action` : l'action qu'elle permet (click, fill, select) ;
- `interactive` : actionnable ou non, sans type, pour comparer un détecteur sans classes.
"""

from collections.abc import Callable, Sequence
from dataclasses import dataclass, field

import numpy as np

from sbc_vision.contracts.perception import ElementKind
from sbc_vision.perception.boxes import area, iou_matrix
from sbc_vision.perception.ontology import primary_action

IOU_THRESHOLDS = np.round(np.arange(0.5, 0.96, 0.05), 2)
RECALL_POINTS = np.linspace(0.0, 1.0, 101)
# Seuils de taille de COCO, en pixels de la capture (aire de la boîte).
SIZE_BUCKETS = (("small", 0, 32**2), ("medium", 32**2, 96**2), ("large", 96**2, float("inf")))
MAX_DETECTIONS = 300  # par étiquette et par image, comme COCO
BOOTSTRAP_SEED = 0


def kind_label(kind: str) -> str | None:
    return kind


def action_label(kind: str) -> str | None:
    action = primary_action(ElementKind(kind))
    return action.value if action else None


def interactive_label(kind: str) -> str | None:
    return "interactive" if action_label(kind) else None


LEVELS: dict[str, Callable[[str], str | None]] = {
    "kind": kind_label,
    "action": action_label,
    "interactive": interactive_label,
}


@dataclass
class ImageBoxes:
    kinds: list[str]
    boxes: np.ndarray  # (n, 4) x1, y1, x2, y2
    scores: np.ndarray | None = None  # prédictions seulement

    def __post_init__(self):
        self.boxes = np.asarray(self.boxes, dtype=np.float64).reshape(-1, 4)
        if self.scores is not None:
            self.scores = np.asarray(self.scores, dtype=np.float64).reshape(-1)
        if np.any(self.boxes[:, 2] < self.boxes[:, 0]) or np.any(
            self.boxes[:, 3] < self.boxes[:, 1]
        ):
            raise ValueError("boîte invalide : x2 < x1 ou y2 < y1")
        if len(self.kinds) != len(self.boxes) or (
            self.scores is not None and len(self.scores) != len(self.boxes)
        ):
            raise ValueError("classes, boîtes et scores de longueurs différentes")


def greedy_match(ious: np.ndarray, threshold: float) -> tuple[np.ndarray, np.ndarray]:
    """`ious` : prédictions (triées par score) × vérités. Retourne l'indice apparié ou -1."""
    pred_match = np.full(ious.shape[0], -1)
    gt_taken = np.zeros(ious.shape[1], dtype=bool)
    for p in range(ious.shape[0]):
        candidates = np.where(~gt_taken & (ious[p] >= threshold), ious[p], -1.0)
        if candidates.size and candidates.max() >= threshold:
            g = int(candidates.argmax())
            pred_match[p] = g
            gt_taken[g] = True
    gt_match = np.full(ious.shape[1], -1)
    gt_match[pred_match[pred_match >= 0]] = np.flatnonzero(pred_match >= 0)
    return pred_match, gt_match


@dataclass
class _PerLabel:
    scores: np.ndarray  # scores des prédictions, triés décroissants
    tp: np.ndarray  # (n_pred, n_seuils) booléens
    gt_areas: np.ndarray  # aires des vérités
    gt_hit_05: np.ndarray  # rang (dans `scores`) de la prédiction appariée à IoU 0,5, ou -1


@dataclass
class ImageMatches:
    labels: dict[str, _PerLabel] = field(default_factory=dict)


def _relabel(item: ImageBoxes, mapping: Callable[[str], str | None]):
    labels = [mapping(kind) for kind in item.kinds]
    keep = np.array([label is not None for label in labels], dtype=bool)
    kept = [label for label in labels if label is not None]
    scores = item.scores[keep] if item.scores is not None else None
    return kept, item.boxes[keep], scores


def match_image(
    gt: ImageBoxes, pred: ImageBoxes, mapping: Callable[[str], str | None]
) -> ImageMatches:
    gt_labels, gt_boxes, _ = _relabel(gt, mapping)
    pred_labels, pred_boxes, pred_scores = _relabel(pred, mapping)
    result = ImageMatches()
    for label in set(gt_labels) | set(pred_labels):
        g = np.array([x == label for x in gt_labels], dtype=bool)
        # Comme COCO : tri par score et limite de détections par étiquette et par image.
        p = np.flatnonzero([x == label for x in pred_labels])
        p = p[np.argsort(-pred_scores[p], kind="mergesort")][:MAX_DETECTIONS]
        ious = iou_matrix(pred_boxes[p], gt_boxes[g])
        tp = np.zeros((len(p), len(IOU_THRESHOLDS)), dtype=bool)
        for t, threshold in enumerate(IOU_THRESHOLDS):
            pred_match, gt_match = greedy_match(ious, threshold)
            tp[:, t] = pred_match >= 0
            if t == 0:  # IoU 0,5
                hit_05 = gt_match
        result.labels[label] = _PerLabel(
            scores=pred_scores[p],
            tp=tp,
            gt_areas=area(gt_boxes[g]),
            gt_hit_05=hit_05,
        )
    return result


def _ap_from(scores: np.ndarray, tp: np.ndarray, n_gt: int) -> np.ndarray:
    """AP interpolé sur 101 points de rappel, comme COCO ; une valeur par seuil d'IoU."""
    if n_gt == 0:
        return np.full(tp.shape[1], np.nan)
    if len(scores) == 0:
        return np.zeros(tp.shape[1])
    order = np.argsort(-scores, kind="mergesort")
    tp = tp[order]
    ctp = np.cumsum(tp, axis=0)
    cfp = np.cumsum(~tp, axis=0)
    recall = ctp / n_gt
    precision = ctp / np.maximum(ctp + cfp, np.finfo(np.float64).eps)
    aps = np.zeros(tp.shape[1])
    for t in range(tp.shape[1]):
        envelope = np.maximum.accumulate(precision[::-1, t])[::-1]
        indices = np.searchsorted(recall[:, t], RECALL_POINTS, side="left")
        sampled = np.where(
            indices < len(envelope), envelope[np.minimum(indices, len(envelope) - 1)], 0
        )
        aps[t] = sampled.mean()
    return aps


@dataclass
class MatchedSet:
    """Appariements d'un jeu de test, prêts à être agrégés sur n'importe quelle sélection."""

    images: list[ImageMatches]

    def labels(self) -> list[str]:
        return sorted({label for image in self.images for label in image.labels})

    def _gather(self, label: str, indices: Sequence[int]):
        parts = [self.images[i].labels.get(label) for i in indices]
        parts = [part for part in parts if part is not None]
        if not parts:
            return np.zeros(0), np.zeros((0, len(IOU_THRESHOLDS)), dtype=bool), 0
        scores = np.concatenate([part.scores for part in parts])
        tp = np.concatenate([part.tp for part in parts])
        n_gt = int(sum(len(part.gt_areas) for part in parts))
        return scores, tp, n_gt

    def average_precision(self, indices: Sequence[int] | None = None) -> dict[str, np.ndarray]:
        indices = range(len(self.images)) if indices is None else indices
        return {label: _ap_from(*self._gather(label, indices)) for label in self.labels()}

    def summary(self, indices: Sequence[int] | None = None) -> dict:
        per_label = self.average_precision(indices)
        valid = {label: ap for label, ap in per_label.items() if not np.isnan(ap[0])}
        stacked = (
            np.array(list(valid.values())) if valid else np.full((1, len(IOU_THRESHOLDS)), np.nan)
        )
        return {
            "mAP50": float(np.mean(stacked[:, 0])),
            "mAP50_95": float(np.mean(stacked)),
            "AP50": {label: float(ap[0]) for label, ap in valid.items()},
            "AP50_95": {label: float(ap.mean()) for label, ap in valid.items()},
        }

    def map50(self, indices: Sequence[int]) -> float:
        """Statistique rééchantillonnée par le bootstrap."""
        return self.summary(indices)["mAP50"]

    def operating_point(self, threshold: float, indices: Sequence[int] | None = None) -> dict:
        """Précision, rappel et F1 à IoU 0,5 pour les prédictions de score ≥ `threshold`."""
        indices = range(len(self.images)) if indices is None else indices
        out = {}
        total_tp = total_pred = total_gt = 0
        for label in self.labels():
            scores, tp, n_gt = self._gather(label, indices)
            kept = scores >= threshold
            n_tp, n_pred = int(tp[kept, 0].sum()), int(kept.sum())
            out[label] = _prf(n_tp, n_pred, n_gt)
            total_tp, total_pred, total_gt = total_tp + n_tp, total_pred + n_pred, total_gt + n_gt
        out["_all"] = _prf(total_tp, total_pred, total_gt)
        return out

    def recall_by_size(self, threshold: float, indices: Sequence[int] | None = None) -> dict:
        indices = range(len(self.images)) if indices is None else indices
        hits = {name: [0, 0] for name, _, _ in SIZE_BUCKETS}
        for i in indices:
            for part in self.images[i].labels.values():
                for gt_area, rank in zip(part.gt_areas, part.gt_hit_05, strict=True):
                    found = rank >= 0 and part.scores[rank] >= threshold
                    for name, low, high in SIZE_BUCKETS:
                        if low <= gt_area < high:
                            hits[name][0] += int(found)
                            hits[name][1] += 1
        return {
            name: {"recall": (hit / total) if total else None, "count": total}
            for name, (hit, total) in hits.items()
        }


def _prf(tp: int, n_pred: int, n_gt: int) -> dict:
    precision = tp / n_pred if n_pred else None
    recall = tp / n_gt if n_gt else None
    if precision is None or recall is None or precision + recall == 0:
        f1 = 0.0 if (n_pred or n_gt) else None
    else:
        f1 = 2 * precision * recall / (precision + recall)
    return {
        "precision": precision,
        "recall": recall,
        "f1": f1,
        "tp": tp,
        "pred": n_pred,
        "gt": n_gt,
    }


def match_dataset(gts: Sequence[ImageBoxes], preds: Sequence[ImageBoxes], level: str) -> MatchedSet:
    mapping = LEVELS[level]
    return MatchedSet(
        images=[match_image(g, p, mapping) for g, p in zip(gts, preds, strict=True)],
    )


def match_levels(gts: Sequence[ImageBoxes], preds: Sequence[ImageBoxes]) -> dict[str, MatchedSet]:
    """Appariements aux trois niveaux (classe, action, interactif)."""
    return {level: match_dataset(gts, preds, level) for level in LEVELS}


def confusion_matrix(
    gts: Sequence[ImageBoxes], preds: Sequence[ImageBoxes], classes: Sequence[str], threshold: float
) -> np.ndarray:
    """Matrice (vérité × prédiction) avec une dernière ligne/colonne « fond ».

    Appariement sans tenir compte de la classe (IoU ≥ 0,5) : une confusion bouton/lien apparaît
    hors diagonale, un élément manqué dans la colonne « fond », une fausse détection dans la
    ligne « fond ».
    """
    index = {name: i for i, name in enumerate(classes)}
    background = len(classes)
    matrix = np.zeros((len(classes) + 1, len(classes) + 1), dtype=np.int64)
    for gt, pred in zip(gts, preds, strict=True):
        keep = pred.scores >= threshold
        order = np.argsort(-pred.scores[keep], kind="stable")
        pred_kinds = [k for k, kept in zip(pred.kinds, keep, strict=True) if kept]
        pred_kinds = [pred_kinds[i] for i in order]
        pred_match, gt_match = greedy_match(iou_matrix(pred.boxes[keep][order], gt.boxes), 0.5)
        for g, kind in enumerate(gt.kinds):
            column = index[pred_kinds[gt_match[g]]] if gt_match[g] >= 0 else background
            matrix[index[kind], column] += 1
        for p, kind in enumerate(pred_kinds):
            if pred_match[p] < 0:
                matrix[background, index[kind]] += 1
    return matrix


def _resamples(n_images: int, groups: Sequence[str] | None, samples: int):
    """Tirages avec remise. Avec `groups`, on tire des groupes entiers (un site, une page) : les
    captures d'un même groupe ne sont pas indépendantes."""
    rng = np.random.default_rng(BOOTSTRAP_SEED)
    clusters = _clusters(n_images, groups)
    for _ in range(samples):
        picked = rng.integers(0, len(clusters), len(clusters))
        yield [i for c in picked for i in clusters[c]]


def bootstrap_interval(
    statistic: Callable[[Sequence[int]], float],
    n_images: int,
    groups: Sequence[str] | None,
    samples: int,
) -> tuple[float, float]:
    """Intervalle percentile à 95 %. Un tirage sans aucune vérité n'a pas de mAP : il est
    écarté, comme dans `paired_bootstrap`."""
    values = np.array([statistic(indices) for indices in _resamples(n_images, groups, samples)])
    values = values[~np.isnan(values)]
    return float(np.quantile(values, 0.025)), float(np.quantile(values, 0.975))


def paired_bootstrap(
    statistic_a: Callable[[Sequence[int]], float],
    statistic_b: Callable[[Sequence[int]], float],
    n_images: int,
    groups: Sequence[str] | None,
    samples: int,
) -> dict:
    """Écart A − B sur les mêmes tirages, et part des tirages où A ne fait pas mieux."""
    diffs = np.array(
        [statistic_a(i) - statistic_b(i) for i in _resamples(n_images, groups, samples)]
    )
    diffs = diffs[~np.isnan(diffs)]
    return {
        "mean_diff": float(diffs.mean()),
        "ci95": (float(np.quantile(diffs, 0.025)), float(np.quantile(diffs, 0.975))),
        "p_not_better": float((diffs <= 0).mean()),
    }


def _clusters(n_images: int, groups: Sequence[str] | None) -> list[list[int]]:
    if groups is None:
        return [[i] for i in range(n_images)]
    by_group: dict[str, list[int]] = {}
    for i, group in enumerate(groups):
        by_group.setdefault(group, []).append(i)
    return list(by_group.values())
