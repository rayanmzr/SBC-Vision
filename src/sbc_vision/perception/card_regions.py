"""Zones de texte d'une carte de joueur détectée, à lire par l'OCR.

Une carte EA FC a une disposition fixe : la note en haut à gauche, le poste dessous, le nom vers
les deux tiers de la hauteur, puis la ligne des statistiques. Les proportions viennent de huit
visuels officiels de cartes FC 27 affichés par EasySBC, mesurés sur une grille de 10 %. Elles
valent pour une carte entière (largeur / hauteur ≈ 0,72) : une boîte coupée par le bord de
l'écran, ou d'autres proportions, n'a pas de zones fiables et est refusée. À vérifier sur la
Web App réelle avant de s'y fier.

Sortie au format des régions de l'OCR (`element_id`, `field`, `bbox`).
"""

from sbc_vision.contracts.perception import BoundingBox, DetectedElement, ElementKind

CARD_ASPECT = (0.68, 0.76)  # largeur / hauteur d'une carte entière
# Zones en fractions de la carte : gauche, haut, droite, bas.
FIELDS: dict[str, tuple[float, float, float, float]] = {
    "rating": (0.10, 0.22, 0.34, 0.35),
    "position": (0.10, 0.34, 0.34, 0.42),
    "name": (0.10, 0.64, 0.90, 0.74),
    "stats": (0.08, 0.72, 0.92, 0.83),
}


def card_regions(element: DetectedElement, layout="card") -> list[dict]:
    """Régions `rating`, `position`, `name` et `stats` d'une carte, en pixels de la capture."""
    if element.kind is not ElementKind.CARD:
        raise ValueError(f"{element.id} n'est pas une carte ({element.kind})")
    box = element.bbox
    aspect = box.width / box.height
    limits = (0.58, 0.85) if layout == "club-list" else CARD_ASPECT
    if layout not in {"card", "club-list"}:
        raise ValueError("Présentation attendue : card ou club-list.")
    if not limits[0] <= aspect <= limits[1]:
        raise ValueError(f"{element.id} : proportions {aspect:.2f}, pas une carte entière")
    fields = FIELDS
    if layout == "club-list":
        # Dans la liste du club, nom et statistiques sont imprimés à droite de la miniature.
        fields = {
            "rating": (0.15, 0.26, 0.40, 0.41),
            "position": (0.10, 0.40, 0.36, 0.49),
            "name": (1.04, 0.10, 3.55, 0.40),
            "stats": (1.04, 0.54, 3.55, 0.84),
        }
    regions = []
    for field, (left, top, right, bottom) in fields.items():
        x, y = box.x + round(left * box.width), box.y + round(top * box.height)
        width = round((right - left) * box.width)
        height = round((bottom - top) * box.height)
        regions.append(
            {
                "element_id": element.id,
                "field": field,
                "bbox": BoundingBox(x=x, y=y, width=width, height=height),
            }
        )
    return regions
