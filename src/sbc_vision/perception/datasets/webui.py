"""Étiquettes WebUI reconstruites depuis l'arbre d'accessibilité complet.

La version « elements » publiée sur Hugging Face ne garde que les nœuds feuilles : un bouton qui
contient une icône et un texte n'y apparaît que comme du texte. Ici, chaque nœud interactif garde
son rôle et sa boîte entière (`bb`), puis on écarte ce qui n'est pas visible dans la capture.

Coordonnées : `bb` est en pixels CSS dans le repère de la zone d'affichage, la capture en pixels
physiques ; l'échelle entre les deux se lit sur la page (`viewport_scale`).
"""

import gzip
import json
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urlsplit

import numpy as np

from sbc_vision.contracts.perception import ElementKind
from sbc_vision.perception.boxes import iou_matrix

ROLE_TO_KIND: dict[str, ElementKind] = {
    "button": ElementKind.BUTTON,
    "menuitem": ElementKind.BUTTON,
    "tab": ElementKind.BUTTON,
    "link": ElementKind.LINK,
    "textbox": ElementKind.INPUT,
    "searchbox": ElementKind.INPUT,
    "spinbutton": ElementKind.INPUT,
    "combobox": ElementKind.MENU,
    "listbox": ElementKind.MENU,
    "PopUpButton": ElementKind.MENU,
    "checkbox": ElementKind.CHECKBOX,
    "radio": ElementKind.CHECKBOX,
    "switch": ElementKind.CHECKBOX,
    "menuitemcheckbox": ElementKind.CHECKBOX,
    "menuitemradio": ElementKind.CHECKBOX,
}

# Deux nœuds imbriqués qui couvrent la même zone (un lien autour d'un bouton) ne donnent qu'un
# élément : le plus spécifique.
KIND_PRIORITY: tuple[ElementKind, ...] = (
    ElementKind.INPUT,
    ElementKind.CHECKBOX,
    ElementKind.MENU,
    ElementKind.BUTTON,
    ElementKind.LINK,
)

# Tailles d'écran retenues : les quatre d'ordinateur. La Web App FC 27 se pilote sur PC, et le
# sujet demande de généraliser à des sites jamais vus, pas à d'autres appareils.
DESKTOP_DEVICES = ("default_1280-720", "default_1366-768", "default_1536-864", "default_1920-1080")


# Règles d'étiquetage, en pixels CSS : côté et aire minimaux, part visible minimale, part de
# l'écran au-delà de laquelle un nœud est un conteneur de mise en page, IoU de deux nœuds
# imbriqués qui ne donnent qu'un élément.
MIN_SIDE_CSS = 4.0
MIN_AREA_CSS = 64.0
MIN_VISIBLE_FRACTION = 0.5
MAX_AREA_FRACTION = 0.6
DUPLICATE_IOU = 0.8


@dataclass(frozen=True)
class LabeledElement:
    kind: ElementKind
    box: tuple[float, float, float, float]  # x1, y1, x2, y2 en pixels de la capture
    role: str
    name: str
    node_id: str


def viewport_scale(axtree: dict, boxes: dict, image_size: tuple[int, int]) -> float:
    """Pixels de capture par pixel CSS, lus sur la zone d'affichage de la page (RootWebArea).

    1 sur un écran standard, 2 sur un écran haute densité ; une page mise en page plus large que
    l'écran puis réduite donne moins. Une capture qui n'a pas les proportions de la zone
    d'affichage est refusée : ses boîtes ne seraient pas à leur place.
    """
    view = boxes.get(str(root_node(axtree)["backendDOMNodeId"]))
    if not view or view["width"] <= 0 or view["height"] <= 0:
        raise ValueError("zone d'affichage sans boîte")
    scale_x, scale_y = image_size[0] / view["width"], image_size[1] / view["height"]
    if abs(scale_x - scale_y) > 0.02 * scale_x:
        raise ValueError(
            f"capture et zone d'affichage disproportionnées ({scale_x:.3f} / {scale_y:.3f})"
        )
    return scale_x


def root_node(axtree: dict) -> dict:
    """Nœud de la zone d'affichage (RootWebArea), unique dans une page."""
    roots = [n for n in axtree["nodes"] if n.get("role", {}).get("value") == "RootWebArea"]
    if len(roots) != 1:
        raise ValueError(f"{len(roots)} zones d'affichage")
    return roots[0]


def _is_hidden(style: dict | None) -> bool:
    if not style:
        return False
    if not isinstance(style, dict):
        # Quelques pages n'ont que les noms des propriétés, sans valeurs : la visibilité n'y
        # est pas vérifiable, la page est écartée par l'appelant.
        raise ValueError("styles calculés sans valeurs")
    return (
        style.get("display") == "none"
        or style.get("visibility") in ("hidden", "collapse")
        or style.get("opacity") == "0"
    )


def _kind(node: dict) -> ElementKind | None:
    role = node.get("role", {}).get("value")
    kind = ROLE_TO_KIND.get(role)
    if kind is ElementKind.MENU and role == "combobox":
        # Un combobox éditable (recherche avec suggestions) se remplit au clavier.
        names = {prop.get("name") for prop in node.get("properties", [])}
        if "editable" in names:
            return ElementKind.INPUT
    return kind


def label_page(
    axtree: dict,
    boxes: dict,
    styles: dict,
    image_size: tuple[int, int],
    scale: float,
) -> list[LabeledElement]:
    """Éléments interactifs visibles d'une page, dans le repère de la capture."""
    nodes = {node["nodeId"]: node for node in axtree["nodes"]}
    width, height = image_size
    view_w, view_h = width / scale, height / scale

    def hidden_by_ancestor(node: dict) -> bool:
        current = node
        while current is not None:
            if _is_hidden(styles.get(str(current.get("backendDOMNodeId")))):
                return True
            current = nodes.get(current.get("parentId"))
        return False

    candidates: list[LabeledElement] = []
    for node in axtree["nodes"]:
        if node.get("ignored"):
            continue
        kind = _kind(node)
        if kind is None:
            continue
        rect = boxes.get(str(node.get("backendDOMNodeId")))
        if not rect or rect["width"] <= 0 or rect["height"] <= 0:
            continue
        if hidden_by_ancestor(node):
            continue
        x1, y1 = rect["x"], rect["y"]
        x2, y2 = x1 + rect["width"], y1 + rect["height"]
        cx1, cy1 = max(0.0, x1), max(0.0, y1)
        cx2, cy2 = min(view_w, x2), min(view_h, y2)
        if cx2 - cx1 < MIN_SIDE_CSS or cy2 - cy1 < MIN_SIDE_CSS:
            continue
        clipped_area = (cx2 - cx1) * (cy2 - cy1)
        if clipped_area < MIN_AREA_CSS:
            continue
        if clipped_area < MIN_VISIBLE_FRACTION * rect["width"] * rect["height"]:
            continue
        if clipped_area > MAX_AREA_FRACTION * view_w * view_h:
            continue
        candidates.append(
            LabeledElement(
                kind=kind,
                box=(cx1 * scale, cy1 * scale, cx2 * scale, cy2 * scale),
                role=node["role"]["value"],
                name=str(node.get("name", {}).get("value", ""))[:200],
                node_id=str(node["nodeId"]),
            )
        )

    kept: list[LabeledElement] = []
    for element in sorted(candidates, key=lambda e: KIND_PRIORITY.index(e.kind)):
        others = np.array([other.box for other in kept]).reshape(-1, 4)
        if not (iou_matrix(np.array([element.box]), others) >= DUPLICATE_IOU).any():
            kept.append(element)
    return kept


@dataclass(frozen=True)
class WebUIPage:
    sample_id: str
    device: str
    screenshot: Path
    url: str

    @property
    def domain(self) -> str:
        host = urlsplit(self.url).hostname
        if not host:
            raise ValueError(f"URL sans domaine : {self.url}")
        return host.removeprefix("www.")

    def _read_json(self, suffix: str) -> dict:
        path = self.screenshot.with_name(f"{self.device}-{suffix}")
        with gzip.open(path, "rt", encoding="utf-8") as handle:
            return json.load(handle)

    def labels(self, image_size: tuple[int, int]) -> tuple[float, list[LabeledElement]]:
        """Échelle de la capture et éléments étiquetés."""
        axtree, boxes = self._read_json("axtree.json.gz"), self._read_json("bb.json.gz")
        scale = viewport_scale(axtree, boxes, image_size)
        return scale, label_page(axtree, boxes, self._read_json("style.json.gz"), image_size, scale)


def iter_pages(sample_dir: Path) -> list[WebUIPage]:
    """Captures d'ordinateur d'un échantillon dont tous les fichiers nécessaires sont présents."""
    pages = []
    for device in DESKTOP_DEVICES:
        files = [
            sample_dir / f"{device}-{suffix}"
            for suffix in ("screenshot.webp", "axtree.json.gz", "bb.json.gz", "style.json.gz")
        ]
        url_file = sample_dir / f"{device}-url.txt"
        if all(path.is_file() for path in files) and url_file.is_file():
            pages.append(
                WebUIPage(
                    sample_id=sample_dir.name,
                    device=device,
                    screenshot=files[0],
                    url=url_file.read_text(encoding="utf-8").strip(),
                )
            )
    return pages
