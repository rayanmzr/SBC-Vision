"""Contrat de sortie en pixels, version 0.1."""

from enum import StrEnum
from typing import Literal, Self

from pydantic import BaseModel, ConfigDict, Field, model_validator


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class ElementKind(StrEnum):
    BUTTON = "button"
    INPUT = "input"
    LINK = "link"
    MENU = "menu"
    CHECKBOX = "checkbox"
    CARD = "card"
    SLOT = "slot"
    TEXT = "text"


class ActionKind(StrEnum):
    CLICK = "click"
    FILL = "fill"
    SELECT = "select"
    SCROLL = "scroll"


class ImageSize(StrictModel):
    width: int = Field(gt=0, strict=True)
    height: int = Field(gt=0, strict=True)


class BoundingBox(StrictModel):
    """Boîte dans la capture : x, y en haut à gauche ; largeur/hauteur en pixels."""

    x: int = Field(ge=0, strict=True)
    y: int = Field(ge=0, strict=True)
    width: int = Field(gt=0, strict=True)
    height: int = Field(gt=0, strict=True)


class DetectedElement(StrictModel):
    id: str = Field(min_length=1)
    kind: ElementKind
    bbox: BoundingBox
    text: str | None = None
    confidence: float = Field(ge=0, le=1)
    actions: list[ActionKind] = Field(default_factory=list)

    @model_validator(mode="after")
    def actions_are_unique(self) -> Self:
        if len(self.actions) != len(set(self.actions)):
            raise ValueError("actions must be unique")
        return self


class PerceptionResponse(StrictModel):
    schema_version: Literal["0.1"] = "0.1"
    capture_id: str = Field(min_length=1)
    image: ImageSize
    model_name: str = Field(min_length=1)
    elements: list[DetectedElement]

    @model_validator(mode="after")
    def elements_fit_capture(self) -> Self:
        ids: set[str] = set()
        for element in self.elements:
            if element.id in ids:
                raise ValueError(f"duplicate element id: {element.id}")
            ids.add(element.id)
            box = element.bbox
            if box.x + box.width > self.image.width or box.y + box.height > self.image.height:
                raise ValueError(f"bounding box outside capture: {element.id}")
        return self
