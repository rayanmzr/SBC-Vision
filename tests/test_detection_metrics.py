import pytest

# Dépendances de l'extra `vision` : sans elles (`make install`), ces tests sont ignorés.
np = pytest.importorskip("numpy")

from sbc_vision.perception.evaluation.metrics import (  # noqa: E402
    ImageBoxes,
    bootstrap_interval,
    confusion_matrix,
    match_dataset,
    paired_bootstrap,
)


def gt(kinds, boxes):
    return ImageBoxes(kinds=list(kinds), boxes=boxes)


def pred(kinds, boxes, scores):
    return ImageBoxes(kinds=list(kinds), boxes=boxes, scores=scores)


BOXES = [[10, 10, 110, 50], [200, 10, 300, 50], [10, 100, 60, 120]]


def test_perfect_predictions_score_one_at_every_level():
    gts = [gt(["button", "link", "checkbox"], BOXES)]
    preds = [pred(["button", "link", "checkbox"], BOXES, [0.9, 0.8, 0.7])]
    for level in ("kind", "action", "interactive"):
        summary = match_dataset(gts, preds, level).summary()
        assert summary["mAP50"] == pytest.approx(1.0)
        assert summary["mAP50_95"] == pytest.approx(1.0)


def test_button_link_confusion_costs_kind_but_not_action():
    gts = [gt(["button", "link"], BOXES[:2])]
    preds = [pred(["link", "button"], BOXES[:2], [0.9, 0.8])]
    assert match_dataset(gts, preds, "kind").summary()["mAP50"] == pytest.approx(0.0)
    assert match_dataset(gts, preds, "action").summary()["mAP50"] == pytest.approx(1.0)


def test_operating_point_counts_matches_above_threshold():
    gts = [gt(["button", "button"], BOXES[:2])]
    preds = [pred(["button", "button", "button"], BOXES, [0.9, 0.3, 0.8])]
    point = match_dataset(gts, preds, "kind").operating_point(0.5)["button"]
    # Au-dessus de 0,5 : une vraie détection et une fausse (la troisième boîte).
    assert (point["tp"], point["pred"], point["gt"]) == (1, 2, 2)
    assert point["precision"] == pytest.approx(0.5)
    assert point["recall"] == pytest.approx(0.5)


def test_confusion_matrix_has_background_row_and_column():
    gts = [gt(["button", "link"], BOXES[:2])]
    preds = [pred(["link", "input"], [BOXES[0], BOXES[2]], [0.9, 0.9])]
    classes = ["button", "input", "link"]
    matrix = confusion_matrix(gts, preds, classes, threshold=0.5)
    assert matrix[0, 2] == 1  # bouton vu comme lien
    assert matrix[2, 3] == 1  # lien manqué
    assert matrix[3, 1] == 1  # champ inventé


def test_recall_by_size_uses_coco_area_buckets():
    gts = [gt(["checkbox", "button"], [[0, 0, 16, 16], [0, 100, 200, 160]])]
    preds = [pred(["button"], [[0, 100, 200, 160]], [0.9])]
    sizes = match_dataset(gts, preds, "interactive").recall_by_size(0.5)
    assert sizes["small"] == {"recall": 0.0, "count": 1}
    assert sizes["large"] == {"recall": 1.0, "count": 1}


def test_bootstrap_interval_brackets_a_stable_statistic():
    rng = np.random.default_rng(1)
    values = rng.normal(0.6, 0.05, 200)
    low, high = bootstrap_interval(lambda idx: float(values[list(idx)].mean()), len(values))
    assert low < values.mean() < high
    assert high - low < 0.03


def _random_dataset(seed, n_images=40, classes=("button", "link", "input")):
    rng = np.random.default_rng(seed)
    gts, preds = [], []
    for _ in range(n_images):
        n = int(rng.integers(0, 12))
        xy = rng.uniform(0, 900, (n, 2))
        wh = rng.uniform(8, 200, (n, 2))
        boxes = np.hstack([xy, xy + wh])
        kinds = list(rng.choice(classes, n))
        gts.append(gt(kinds, boxes))
        keep = rng.random(n) < 0.8
        jitter = rng.normal(0, 6, (n, 4))
        p_boxes = (boxes + jitter)[keep]
        p_boxes[:, 2:] = np.maximum(p_boxes[:, 2:], p_boxes[:, :2] + 1)
        p_kinds = [k if rng.random() < 0.85 else rng.choice(classes) for k in np.array(kinds)[keep]]
        m = int(rng.integers(0, 5))
        fxy = rng.uniform(0, 900, (m, 2))
        fake = np.hstack([fxy, fxy + rng.uniform(8, 200, (m, 2))])
        preds.append(
            pred(
                p_kinds + list(rng.choice(classes, m)),
                np.vstack([p_boxes, fake]) if len(fake) else p_boxes,
                rng.random(len(p_kinds) + m),
            )
        )
    return gts, preds


def test_paired_bootstrap_sees_a_consistent_gap_and_no_gap_against_itself():
    # Dix sites : A trouve les deux éléments de chaque page, B un seul.
    gts = [gt(["button", "link"], BOXES[:2]) for _ in range(10)]
    better = [pred(["button", "link"], BOXES[:2], [0.9, 0.8]) for _ in range(10)]
    worse = [pred(["button"], BOXES[:1], [0.9]) for _ in range(10)]
    a, b = match_dataset(gts, better, "kind"), match_dataset(gts, worse, "kind")
    groups = [f"site{i}" for i in range(10)]

    def stat(m):
        return lambda idx: m.summary(idx)["mAP50"]

    gap = paired_bootstrap(stat(a), stat(b), 10, groups, samples=200)
    assert gap["mean_diff"] == pytest.approx(0.5)
    assert gap["p_not_better"] == 0
    same = paired_bootstrap(stat(a), stat(a), 10, groups, samples=200)
    assert same["mean_diff"] == 0 and same["p_not_better"] == 1


def test_map_matches_pycocotools():
    coco_module = pytest.importorskip("pycocotools.coco")
    cocoeval = pytest.importorskip("pycocotools.cocoeval")
    classes = ("button", "link", "input")
    gts, preds = _random_dataset(7, classes=classes)
    ids = {name: i + 1 for i, name in enumerate(classes)}
    images, annotations, results = [], [], []
    for image_id, (g, p) in enumerate(zip(gts, preds, strict=True), start=1):
        images.append({"id": image_id, "width": 1200, "height": 1200})
        for kind, (x1, y1, x2, y2) in zip(g.kinds, g.boxes, strict=True):
            annotations.append(
                {
                    "id": len(annotations) + 1,
                    "image_id": image_id,
                    "category_id": ids[kind],
                    "bbox": [x1, y1, x2 - x1, y2 - y1],
                    "area": (x2 - x1) * (y2 - y1),
                    "iscrowd": 0,
                }
            )
        for kind, (x1, y1, x2, y2), score in zip(p.kinds, p.boxes, p.scores, strict=True):
            results.append(
                {
                    "image_id": image_id,
                    "category_id": ids[kind],
                    "bbox": [x1, y1, x2 - x1, y2 - y1],
                    "score": float(score),
                }
            )
    coco = coco_module.COCO()
    coco.dataset = {
        "images": images,
        "annotations": annotations,
        "categories": [{"id": i, "name": n} for n, i in ids.items()],
    }
    coco.createIndex()
    evaluator = cocoeval.COCOeval(coco, coco.loadRes(results), "bbox")
    evaluator.params.maxDets = [300, 300, 300]
    evaluator.evaluate()
    evaluator.accumulate()
    precision = evaluator.eval["precision"][:, :, :, 0, -1]  # aire « all », maxDets 300
    reference_50 = float(np.mean([np.mean(precision[0, :, k]) for k in range(len(classes))]))
    reference = float(np.mean(precision))

    summary = match_dataset(gts, preds, "kind", max_dets=300).summary()
    assert summary["mAP50"] == pytest.approx(reference_50, abs=1e-9)
    assert summary["mAP50_95"] == pytest.approx(reference, abs=1e-9)
