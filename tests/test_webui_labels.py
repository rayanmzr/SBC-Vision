import pytest

from sbc_vision.contracts.perception import ElementKind
from sbc_vision.perception.datasets.records import BoxRecord, ImageRecord, coco_document
from sbc_vision.perception.datasets.webui import label_page, viewport_scale


def node(node_id, role, backend, parent=None, children=(), name="", properties=()):
    return {
        "nodeId": node_id,
        "ignored": False,
        "role": {"type": "role", "value": role},
        "name": {"type": "computedString", "value": name},
        "properties": list(properties),
        "parentId": parent,
        "childIds": list(children),
        "backendDOMNodeId": backend,
    }


def rect(x, y, w, h):
    return {"x": x, "y": y, "width": w, "height": h}


def page(nodes, boxes, styles=None, size=(1280, 720), scale=1):
    return label_page({"nodes": nodes}, boxes, styles or {}, size, scale)


def test_composite_button_keeps_its_role_and_full_box():
    # Le cas perdu par la version « elements » : icône + texte dans un bouton.
    nodes = [
        node("1", "RootWebArea", 1, children=["2"]),
        node("2", "button", 2, parent="1", children=["3", "4"], name="Continue with Google"),
        node("3", "img", 3, parent="2"),
        node("4", "StaticText", 4, parent="2", name="Continue with Google"),
    ]
    boxes = {
        "1": rect(0, 0, 1280, 720),
        "2": rect(400, 300, 320, 52),
        "3": rect(417, 316, 20, 20),
        "4": rect(453, 317, 151, 18),
    }
    [element] = page(nodes, boxes)
    assert element.kind is ElementKind.BUTTON
    assert element.box == (400, 300, 720, 352)


def test_hidden_ancestor_removes_element():
    nodes = [
        node("1", "RootWebArea", 1, children=["2"]),
        node("2", "generic", 2, parent="1", children=["3"]),
        node("3", "link", 3, parent="2", name="Menu"),
    ]
    boxes = {"1": rect(0, 0, 1280, 720), "2": rect(0, 0, 300, 300), "3": rect(10, 10, 80, 20)}
    assert page(nodes, boxes, styles={"2": {"opacity": "0"}}) == []
    assert page(nodes, boxes, styles={"3": {"visibility": "hidden"}}) == []
    assert len(page(nodes, boxes, styles={"2": {"opacity": "1"}})) == 1


def test_offscreen_elements_are_dropped_and_partial_ones_clipped():
    nodes = [
        node("1", "RootWebArea", 1, children=["2", "3", "4"]),
        node("2", "button", 2, parent="1"),
        node("3", "button", 3, parent="1"),
        node("4", "button", 4, parent="1"),
    ]
    boxes = {
        "1": rect(0, 0, 1280, 720),
        "2": rect(100, 900, 100, 40),  # sous le pli
        "3": rect(100, 700, 100, 40),  # visible à moitié : gardé, rogné
        "4": rect(100, 710, 100, 40),  # visible au quart : écarté
    }
    [element] = page(nodes, boxes)
    assert element.box == (100, 700, 200, 720)


def test_link_wrapping_same_button_gives_one_button():
    nodes = [
        node("1", "RootWebArea", 1, children=["2"]),
        node("2", "link", 2, parent="1", children=["3"]),
        node("3", "button", 3, parent="2", name="Acheter"),
    ]
    boxes = {"1": rect(0, 0, 1280, 720), "2": rect(50, 50, 120, 40), "3": rect(51, 51, 118, 38)}
    assert [e.kind for e in page(nodes, boxes)] == [ElementKind.BUTTON]


def test_editable_combobox_is_an_input():
    editable = [{"name": "editable", "value": {"type": "token", "value": "plaintext"}}]
    nodes = [
        node("1", "RootWebArea", 1, children=["2", "3"]),
        node("2", "combobox", 2, parent="1", properties=editable),
        node("3", "combobox", 3, parent="1"),
    ]
    boxes = {"1": rect(0, 0, 1280, 720), "2": rect(10, 10, 300, 40), "3": rect(10, 80, 200, 40)}
    kinds = sorted(e.kind.value for e in page(nodes, boxes))
    assert kinds == ["input", "menu"]


def test_scale_comes_from_the_viewport_box():
    nodes = [node("1", "RootWebArea", 1, children=["2"]), node("2", "checkbox", 2, parent="1")]
    standard = {"1": rect(0, 0, 1280, 720), "2": rect(20, 30, 16, 16)}
    assert viewport_scale({"nodes": nodes}, standard, (1280, 720)) == 1
    # Écran haute densité : deux pixels de capture par pixel CSS.
    scale = viewport_scale({"nodes": nodes}, standard, (2560, 1440))
    assert scale == 2
    [element] = page(nodes, standard, size=(2560, 1440), scale=scale)
    assert element.box == (40, 60, 72, 92)


def test_viewport_and_capture_of_different_proportions_are_rejected():
    nodes = [node("1", "RootWebArea", 1)]
    with pytest.raises(ValueError):
        viewport_scale({"nodes": nodes}, {"1": rect(0, 0, 390, 600)}, (1170, 2532))


def test_coco_export_uses_one_based_categories_and_xywh():
    image = ImageRecord(1, "a.webp", 1280, 720, "webui", "train", "x.org", "1", "d", "0" * 64)
    document = coco_document([image], [BoxRecord(1, ElementKind.BUTTON, (10, 20, 110, 60))])
    [annotation] = document["annotations"]
    assert annotation["category_id"] == 1
    assert annotation["bbox"] == [10, 20, 100, 40]
    assert [c["name"] for c in document["categories"]][:2] == ["button", "input"]


def test_page_with_valueless_styles_is_rejected():
    nodes = [node("1", "RootWebArea", 1, children=["2"]), node("2", "button", 2, parent="1")]
    boxes = {"1": rect(0, 0, 1280, 720), "2": rect(10, 10, 80, 30)}
    with pytest.raises(ValueError):
        page(nodes, boxes, styles={"2": ["display", "opacity"]})
