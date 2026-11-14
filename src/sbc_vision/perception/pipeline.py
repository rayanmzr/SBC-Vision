"""Point de raccordement commun au détecteur de Saber et à l'OCR de Rayan."""

from dataclasses import dataclass
from typing import Protocol

from PIL import Image

from sbc_vision.contracts.perception import PerceptionResponse


@dataclass(frozen=True)
class Capture:
    """Image décodée en mémoire, sans recadrage ni changement de repère."""

    capture_id: str
    image: Image.Image


class UnrecognizedSceneError(Exception):
    """Le pipeline ne peut pas produire une observation utilisable de cette scène."""


class PerceptionPipeline(Protocol):
    async def analyze(self, capture: Capture) -> PerceptionResponse:
        """Détecter, lire puis normaliser ; ne réalise aucune action sur le navigateur.

        L'implémentation doit rester non bloquante et respecter l'annulation.
        Un moteur synchrone devra être exécuté dans un worker adapté.
        """
        ...
