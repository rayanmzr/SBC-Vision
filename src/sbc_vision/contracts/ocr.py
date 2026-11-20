"""Raccord HTTP de l'OCR de Rayan : régions fournies, aucune détection présumée."""

from typing import Literal, Self

from pydantic import BaseModel, ConfigDict, Field, model_validator

from sbc_vision.contracts.geometry import ImageSize
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
