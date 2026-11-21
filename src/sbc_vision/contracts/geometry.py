"""Repère commun à la détection et à l'OCR, sans dépendance entre leurs modèles."""

from pydantic import BaseModel, ConfigDict, Field


class ImageSize(BaseModel):
    model_config = ConfigDict(extra="forbid")
    width: int = Field(gt=0, strict=True)
    height: int = Field(gt=0, strict=True)


class BoundingBox(BaseModel):
    model_config = ConfigDict(extra="forbid")
    x: int = Field(ge=0, strict=True)
    y: int = Field(ge=0, strict=True)
    width: int = Field(gt=0, strict=True)
    height: int = Field(gt=0, strict=True)
