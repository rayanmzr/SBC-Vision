"""Raccord HTTP de l'OCR de Rayan : régions fournies, aucune détection présumée."""

from typing import Literal, Self

from pydantic import BaseModel, ConfigDict, Field, model_validator

from sbc_vision.contracts.geometry import BoundingBox, ImageSize
from sbc_vision.sbc_engine.models import CardReading, Challenge, OcrInput, TextRegion


class OcrAnalysisRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    image: ImageSize
    specification: OcrInput
    minimum_confidence: float = Field(default=0.75, ge=0, le=1, allow_inf_nan=False)
    market: Literal["ps", "pc"] = "pc"
    budget: int = Field(default=0, ge=0, le=1_000_000_000, strict=True)

    @model_validator(mode="after")
    def bounded_regions(self) -> Self:
        if len(self.specification.capture_id) > 128 or len(self.specification.regions) > 128:
            raise ValueError("Identifiant limité à 128 caractères et à 128 régions par capture.")
        for region in self.specification.regions:
            box = region.bbox
            if (
                len(region.element_id) > 128
                or box.x + box.width > self.image.width
                or box.y + box.height > self.image.height
            ):
                raise ValueError("Identifiant trop long ou région hors de l'image déclarée.")
        return self


class OcrWord(BaseModel):
    text: str
    confidence: float = Field(ge=0, le=1, allow_inf_nan=False)
    x: float
    y: float
    width: float = Field(ge=0)
    height: float = Field(ge=0)
    line: tuple[int, int, int]


class RegionReading(TextRegion):
    text: str
    confidence: float = Field(ge=0, le=1, allow_inf_nan=False)
    words: list[OcrWord]
    method: Literal["global", "region"]


class OcrCard(BaseModel):
    element_id: str
    reading: CardReading | None
    candidate_ids: list[int]
    issues: list[str]
    needs_confirmation: Literal[True]


class OcrAnalysisResponse(BaseModel):
    capture_id: str
    image: ImageSize
    engine: Literal["rayan-tesseract"] = "rayan-tesseract"
    engine_version: str
    language: str
    region_source: Literal["provided", "detected"] = "provided"
    automatic_detection: bool = False
    minimum_confidence: float
    regions: list[RegionReading]
    cards: list[OcrCard]
    positions: list[str]
    challenge_ready: bool
    challenge: Challenge | None
    challenge_issues: list[str]


class VisionRow(BaseModel):
    model_config = ConfigDict(extra="forbid")
    element_id: str
    bbox: BoundingBox
    detector: Literal["yolo", "opencv-ocr"]


class VisionFrame(BaseModel):
    model_config = ConfigDict(extra="forbid")
    source: Literal["vision"] = "vision"
    capture_id: str
    image: ImageSize
    model_name: str
    image_sha256: str = Field(pattern="^[0-9a-f]{64}$")
    screen_hash: str = Field(pattern="^[0-9a-f]{64}$")
    scene: Literal["players", "club", "other"]
    list_bbox: BoundingBox | None
    controls: dict[Literal["club", "players", "previous", "next"], BoundingBox]
    rows: list[VisionRow]
    ocr: OcrAnalysisResponse | None = None

    @model_validator(mode="after")
    def bounded_observation(self) -> Self:
        boxes = [r.bbox for r in self.rows] + list(self.controls.values())
        if self.list_bbox:
            boxes.append(self.list_bbox)
        if any(
            b.x + b.width > self.image.width or b.y + b.height > self.image.height for b in boxes
        ):
            raise ValueError("Une région vision dépasse la capture.")
        if self.ocr and (self.ocr.capture_id != self.capture_id or self.ocr.image != self.image):
            raise ValueError("L'OCR ne correspond pas à la capture vision.")
        return self
