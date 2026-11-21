"""Pipeline de test explicite : rectangles du laboratoire, jamais des joueurs EA."""

from PIL import ImageChops
from starlette.concurrency import run_in_threadpool

from sbc_vision.contracts.perception import PerceptionResponse
from sbc_vision.perception.pipeline import Capture, UnrecognizedSceneError

MARKERS = (
    ("lab-select", "Sélectionner la carte fictive", (24, 122, 211)),
    ("lab-place", "Placer la carte fictive", (142, 65, 198)),
    ("lab-done", "Carte fictive placée", (20, 160, 110)),
)


class LabColorPipeline:
    """Détection depuis les pixels, hors boucle asynchrone ; aucun poids entraîné."""

    async def analyze(self, capture: Capture) -> PerceptionResponse:
        return await run_in_threadpool(self._analyze, capture)

    def _analyze(self, capture: Capture) -> PerceptionResponse:
        elements = []
        channels = capture.image.split()
        for identifier, label, color in MARKERS:
            masks = [
                channel.point([255 if abs(value - expected) <= 3 else 0 for value in range(256)])
                for channel, expected in zip(channels, color, strict=True)
            ]
            mask = ImageChops.multiply(ImageChops.multiply(masks[0], masks[1]), masks[2])
            bounds = mask.getbbox()
            if bounds is None:
                continue
            left, top, right, bottom = bounds
            width, height = right - left, bottom - top
            count = mask.histogram()[255]
            if width < 24 or height < 20 or count / (width * height) < 0.98:
                raise UnrecognizedSceneError("Repère incomplet ou ambigu.")
            elements.append(
                {
                    "id": identifier,
                    "kind": "text" if identifier == "lab-done" else "button",
                    "bbox": {"x": left, "y": top, "width": width, "height": height},
                    "text": label,
                    "confidence": 1,
                    "actions": [] if identifier == "lab-done" else ["click"],
                }
            )
        if len(elements) != 1:
            raise UnrecognizedSceneError("Un seul état de laboratoire est attendu.")
        return PerceptionResponse.model_validate(
            {
                "schema_version": "0.1",
                "capture_id": capture.capture_id,
                "model_name": "lab-color-api-v1",
                "image": {"width": capture.image.width, "height": capture.image.height},
                "elements": elements,
            }
        )
