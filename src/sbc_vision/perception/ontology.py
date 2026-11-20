"""Classes détectées et actions qui en découlent.

Le détecteur localise les éléments d'interface ; l'action possible se déduit de la classe par une
table fixe, identique pour toutes les approches comparées. Le texte isolé (`text`) n'est pas une
classe du détecteur : il vient de l'étape de lecture.
"""

from sbc_vision.contracts.perception import ActionKind, ElementKind

# Ordre stable : l'indice sert d'identifiant de classe dans les exports COCO et YOLO.
DETECTOR_CLASSES: tuple[ElementKind, ...] = (
    ElementKind.BUTTON,
    ElementKind.INPUT,
    ElementKind.LINK,
    ElementKind.MENU,
    ElementKind.CHECKBOX,
    ElementKind.CARD,
    ElementKind.SLOT,
)

ACTIONS: dict[ElementKind, tuple[ActionKind, ...]] = {
    ElementKind.BUTTON: (ActionKind.CLICK,),
    ElementKind.INPUT: (ActionKind.FILL,),
    ElementKind.LINK: (ActionKind.CLICK,),
    ElementKind.MENU: (ActionKind.SELECT,),
    ElementKind.CHECKBOX: (ActionKind.CLICK,),
    ElementKind.CARD: (ActionKind.CLICK,),
    ElementKind.SLOT: (ActionKind.CLICK,),
    ElementKind.TEXT: (),
}


def class_id(kind: ElementKind) -> int:
    return DETECTOR_CLASSES.index(kind)


def primary_action(kind: ElementKind) -> ActionKind | None:
    """Action retenue pour le score par action ; `None` pour un élément non actionnable."""
    actions = ACTIONS[kind]
    return actions[0] if actions else None
