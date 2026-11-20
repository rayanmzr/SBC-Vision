import numpy as np

from sbc_vision.perception.explain.drise import concentration, explain, random_masks

BOX = (40.0, 40.0, 80.0, 70.0)


class _WhiteSquareDetector:
    """Voit un bouton tant que le carré blanc de sa boîte reste visible."""

    name = "toy"

    def detect(self, image):
        x1, y1, x2, y2 = (int(v) for v in BOX)
        visible = float((image[y1:y2, x1:x2] > 200).mean())  # part du carré restée blanche
        return [("button", BOX, visible)] if visible > 0.5 else []


def test_masks_are_soft_and_cover_about_half_the_image():
    masks = list(random_masks(90, 120, 50, seed=0))
    assert all(m.shape == (90, 120) and 0 <= m.min() and m.max() <= 1 for m in masks)
    assert 0.35 < np.mean([m.mean() for m in masks]) < 0.65


def test_saliency_lands_on_what_makes_the_detection():
    image = np.zeros((120, 160, 3), dtype=np.uint8)
    image[40:70, 40:80] = 255
    [saliency] = explain(_WhiteSquareDetector(), image, [("button", BOX, 1.0)], count=300)
    assert saliency[40:70, 40:80].mean() > saliency[90:, 100:].mean()
    # Sans lien entre la boîte et la détection, la concentration vaudrait 1.
    assert concentration(saliency, BOX) > 3


def test_another_class_at_the_same_place_does_not_count():
    image = np.zeros((120, 160, 3), dtype=np.uint8)
    image[40:70, 40:80] = 255
    [saliency] = explain(_WhiteSquareDetector(), image, [("link", BOX, 1.0)], count=50)
    assert not saliency.any()
