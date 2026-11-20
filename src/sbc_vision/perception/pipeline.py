"""Point de raccordement commun au détecteur de Saber et à l'OCR de Rayan."""

from dataclasses import dataclass
from io import BytesIO
from pathlib import Path
from threading import BoundedSemaphore
from typing import Protocol

from PIL import Image
from starlette.concurrency import run_in_threadpool

from sbc_vision.contracts.perception import PerceptionResponse


@dataclass(frozen=True)
class Capture:
    """Image décodée en mémoire, sans recadrage ni changement de repère."""

    capture_id: str
    image: Image.Image


class UnrecognizedSceneError(Exception):
    """Le pipeline ne peut pas produire une observation utilisable de cette scène."""


class PipelineBusyError(Exception):
    """Une inférence occupe déjà le modèle partagé."""


class PerceptionPipeline(Protocol):
    async def analyze(self, capture: Capture) -> PerceptionResponse:
        """Détecter, lire puis normaliser ; ne réalise aucune action sur le navigateur.

        L'implémentation doit rester non bloquante et respecter l'annulation.
        Un moteur synchrone devra être exécuté dans un worker adapté.
        """
        ...


class DetectorPipeline:
    """Relie le détecteur de Saber aux régions de cartes puis à l'OCR de Rayan."""

    def __init__(
        self, spec: str, minimum=0.61, reader=None, database: Path | None = None, layout="card"
    ):
        import math

        from .detector import load_detector

        if not math.isfinite(minimum) or not 0 <= minimum <= 1:
            raise ValueError("Le seuil de détection doit être compris entre 0 et 1.")
        if layout not in {"card", "club-list"}:
            raise ValueError("Présentation attendue : card ou club-list.")
        self.detector = load_detector(spec)
        self.layout = layout
        self.minimum, self.reader, self.database = minimum, reader, database
        self.slot = BoundedSemaphore(1)

    async def analyze(self, capture: Capture) -> PerceptionResponse:
        # Le worker possède sa copie même si le client annule la requête HTTP.
        return await run_in_threadpool(
            self._analyze, Capture(capture.capture_id, capture.image.copy())
        )

    def _analyze(self, capture: Capture) -> PerceptionResponse:
        import numpy as np

        from sbc_vision.contracts.ocr import OcrAnalysisRequest
        from sbc_vision.perception.card_regions import card_regions
        from sbc_vision.perception.elements import to_elements
        from sbc_vision.perception.ocr_regions import OcrBusyError

        with capture.image as image:
            if not self.slot.acquire(blocking=False):
                raise PipelineBusyError
            try:
                elements = to_elements(
                    self.detector.detect(np.asarray(image)), min_score=self.minimum
                )
                response = PerceptionResponse(
                    capture_id=capture.capture_id,
                    image={"width": image.width, "height": image.height},
                    model_name=self.detector.name,
                    elements=elements,
                )
                regions, skipped = [], []
                for element in elements:
                    if element.kind == "card":
                        try:
                            proposed = card_regions(element, self.layout)
                            if any(
                                r["bbox"].x + r["bbox"].width > image.width
                                or r["bbox"].y + r["bbox"].height > image.height
                                for r in proposed
                            ):
                                raise ValueError("Région hors image.")
                            regions.extend(proposed)
                        except ValueError:
                            skipped.append(
                                f"Carte partielle ou proportions inconnues : {element.id}."
                            )
                if self.reader and regions and len(regions) <= 128:
                    spec = OcrAnalysisRequest(
                        image=response.image,
                        specification={"capture_id": capture.capture_id, "regions": regions},
                    )
                    data = BytesIO()
                    image.save(data, format="PNG")
                    response.ocr = self.reader.analyze(data.getvalue(), spec, self.database)
                    response.ocr.region_source, response.ocr.automatic_detection = "detected", True
                    response.ocr.challenge_issues.extend(skipped)
                    for card in response.ocr.cards:
                        if card.reading and not card.issues:
                            next(
                                e for e in elements if e.id == card.element_id
                            ).text = f"{card.reading.name} · {card.reading.rating}"
                return response
            except OcrBusyError as exc:
                raise PipelineBusyError from exc
            finally:
                self.slot.release()
