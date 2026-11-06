"""Formats des lectures, exemplaires et conditions du solveur."""

from typing import Literal, Self

from pydantic import BaseModel, ConfigDict, Field, model_validator

from sbc_vision.contracts.perception import BoundingBox


class StrictModel(BaseModel):
    # Une lecture invalide doit être corrigée plutôt que convertie silencieusement.
    model_config = ConfigDict(extra="forbid", strict=True, str_strip_whitespace=True)


class TextRegion(StrictModel):
    element_id: str = Field(min_length=1)
    field: Literal["name", "rating", "position", "item_score", "requirements", "slots"]
    bbox: BoundingBox


class OcrInput(StrictModel):
    capture_id: str = Field(min_length=1)
    regions: list[TextRegion] = Field(min_length=1)

    @model_validator(mode="after")
    def unique_fields(self) -> Self:
        keys = [(r.element_id, r.field) for r in self.regions]
        if len(keys) != len(set(keys)):
            raise ValueError("Une seule région par champ et par élément.")
        return self


class CardReading(StrictModel):
    """Attributs lus sur une carte ; ce modèle n'effectue pas encore l'OCR."""

    capture_id: str = Field(min_length=1)
    element_id: str = Field(min_length=1)
    name: str = Field(min_length=1)
    rating: int = Field(ge=1, le=99)
    confidence: float = Field(ge=0, le=1)
    position: str | None = Field(default=None, min_length=1)
    club_id: int | None = Field(default=None, gt=0)
    league_id: int | None = Field(default=None, gt=0)
    nation_id: int | None = Field(default=None, gt=0)
    rare_type: int | None = Field(default=None, ge=0)
    is_rare: bool | None = None


class ClubItem(StrictModel):
    """Un exemplaire possédé, distinct de la version du catalogue."""

    instance_id: str = Field(min_length=1)
    card_id: int = Field(gt=0)
    protected: bool = False
    # None signifie que le caractère échangeable n'a pas été confirmé.
    tradeable: bool | None = None
    source_observation: str = Field(min_length=1)


class Challenge(StrictModel):
    rules_version: Literal["prototype-v1"]
    positions: list[str] = Field(min_length=1, max_length=11)
    market: Literal["ps", "pc"]
    budget: int = Field(ge=0, le=1_000_000_000)
    min_card_rating: int = Field(default=1, ge=1, le=99)
    min_rare: int = Field(default=0, ge=0, le=11)
    nation_id: int | None = Field(default=None, gt=0)
    min_nation: int = Field(default=0, ge=0, le=11)
    league_id: int | None = Field(default=None, gt=0)
    min_league: int = Field(default=0, ge=0, le=11)

    @model_validator(mode="after")
    def check_requirements(self) -> Self:
        if any(not position for position in self.positions):
            raise ValueError("Chaque poste doit être renseigné.")
        if (self.min_nation and self.nation_id is None) or (
            self.min_league and self.league_id is None
        ):
            raise ValueError("Indiquer le pays ou la ligue associé au quota.")
        return self


class Candidate(StrictModel):
    key: str = Field(min_length=1)
    card_id: int = Field(gt=0)
    base_id: int = Field(gt=0)
    name: str = Field(min_length=1)
    rating: int = Field(ge=1, le=99)
    positions: list[str] = Field(min_length=1)
    nation_id: int = Field(gt=0)
    league_id: int = Field(gt=0)
    is_rare: bool
    owned: bool
    protected: bool = False
    # Valeur sacrifiée si possédée, prix d'achat sinon. Un inconnu reste None.
    value: int | None = Field(default=None, gt=0, le=1_000_000_000)
    source_url: str = Field(min_length=1)
    observed_at: str = Field(min_length=1)


class Assignment(StrictModel):
    slot: int = Field(ge=0, le=10)
    candidate_key: str = Field(min_length=1)


class SolverResult(StrictModel):
    status: Literal["optimal", "feasible", "infeasible", "unknown"]
    assignments: list[Assignment] = Field(default_factory=list)
    purchase_cost: int | None = None
    sacrifice_value: int | None = None
    total_cost: int | None = None
    elapsed_seconds: float = 0.0
    excluded_keys: list[str] = Field(default_factory=list)
    errors: list[str] = Field(default_factory=list)
