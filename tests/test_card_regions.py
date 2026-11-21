import pytest

from sbc_vision.contracts.perception import BoundingBox, DetectedElement
from sbc_vision.perception.card_regions import card_regions


def element(kind, width, height):
    box = BoundingBox(x=100, y=50, width=width, height=height)
    return DetectedElement(id="e3", kind=kind, bbox=box, confidence=0.9)


def test_a_whole_card_gives_its_four_text_zones_inside_it():
    regions = card_regions(element("card", 144, 200))
    assert [r["field"] for r in regions] == ["rating", "position", "name", "stats"]
    assert all(r["element_id"] == "e3" for r in regions)
    for region in regions:
        box = region["bbox"]
        assert (
            100 <= box.x and box.x + box.width <= 244 and 50 <= box.y and box.y + box.height <= 250
        )
    rating, name = regions[0]["bbox"], regions[2]["bbox"]
    assert rating.y < name.y and rating.width < name.width


def test_cut_cards_and_other_elements_are_refused():
    with pytest.raises(ValueError):
        card_regions(element("card", 144, 120))  # coupée par le bord de l'écran
    with pytest.raises(ValueError):
        card_regions(element("slot", 144, 200))


def test_ea_club_list_places_name_and_stats_beside_the_miniature():
    regions = {r["field"]: r["bbox"] for r in card_regions(element("card", 156, 234), "club-list")}
    assert regions["name"].x > 256 and regions["stats"].x > 256
    assert regions["rating"].x < 256
    with pytest.raises(ValueError):
        card_regions(element("card", 144, 200), "guess")
