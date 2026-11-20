import numpy as np
import pytest

from sbc_vision.perception.boxes import iou_matrix, nms_per_class


def test_iou_matrix_pairs_every_box():
    a = np.array([[0, 0, 10, 10], [20, 20, 30, 30]], dtype=float)
    b = np.array([[0, 0, 10, 10], [5, 0, 15, 10], [0, 0, 0, 0]], dtype=float)
    ious = iou_matrix(a, b)
    assert ious.shape == (2, 3)
    assert ious[0, 0] == 1 and ious[0, 1] == pytest.approx(50 / 150) and ious[0, 2] == 0
    assert not ious[1].any()
    assert iou_matrix(a, np.zeros((0, 4))).shape == (2, 0)


def test_nms_keeps_the_best_box_per_class_and_never_merges_classes():
    boxes = np.array([[0, 0, 10, 10], [1, 0, 11, 10], [0, 0, 10, 10], [50, 50, 60, 60]], float)
    kinds = ["button", "button", "link", "button"]
    scores = np.array([0.6, 0.9, 0.7, 0.3])
    assert nms_per_class(boxes, kinds, scores, iou=0.5, limit=10) == [1, 2, 3]
    assert nms_per_class(boxes, kinds, scores, iou=0.5, limit=2) == [1, 2]
