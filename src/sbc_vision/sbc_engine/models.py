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
    positions: list[str] = Field(default_factory=list, max_length=11)
    attributes: dict[str, dict[str, int | bool]] = Field(default_factory=dict)

    @model_validator(mode="after")
    def unique_fields(self) -> Self:
        keys = [(r.element_id, r.field) for r in self.regions]
        if len(keys) != len(set(keys)):
            raise ValueError("Une seule région par champ et par élément.")
        allowed = {"club_id", "league_id", "nation_id", "rare_type", "is_rare"}
        if any(set(values) - allowed for values in self.attributes.values()):
            raise ValueError("Attribut visuel non reconnu.")
        return self


class CardReading(StrictModel):
    """Attributs lus sur une carte, à rapprocher des versions du catalogue."""

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
    item_score: int | None = Field(default=None, gt=0, le=1_000_000_000)


class ClubItem(StrictModel):
    """Un exemplaire possédé, distinct de la version du catalogue."""

    instance_id: str = Field(min_length=1)
    card_id: int = Field(gt=0)
    protected: bool = False
    # None signifie que le caractère échangeable n'a pas été confirmé.
    tradeable: bool | None = None
    source_observation: str = Field(min_length=1)
    item_score: int | None = Field(default=None, gt=0, le=1_000_000_000)


class Condition(StrictModel):
    metric: Literal[
        "players",
        "rating",
        "rated",
        "rare",
        "nation",
        "league",
        "club",
        "nations",
        "leagues",
        "clubs",
        "same_nation",
        "same_league",
        "same_club",
        "quality",
        "item_score",
        "team_rating",
        "chemistry",
    ]
    op: Literal["min", "max", "exact"] = "min"
    value: int = Field(ge=0, le=1_000_000_000)
    target: int | str | None = None
    text: str = ""

    @model_validator(mode="after")
    def valid_target(self) -> Self:
        if self.metric in {"rating", "team_rating"} and not 1 <= self.value <= 99:
            raise ValueError("La note doit être comprise entre 1 et 99.")
        if self.metric == "chemistry" and self.value > 33:
            raise ValueError("Le collectif ne peut pas dépasser 33.")
        if self.metric in {"nation", "league", "club", "rated"} and type(self.target) is not int:
            raise ValueError("Cette condition doit indiquer un identifiant ou une note cible.")
        if self.metric == "quality" and self.target not in {"BRONZE", "SILVER", "GOLD"}:
            raise ValueError("Qualité de carte inconnue.")
        return self


class Challenge(StrictModel):
    rules_version: Literal["prototype-v1", "dynamic-v1"]
    mode: Literal["squad", "score"] = "squad"
    positions: list[str] = Field(default_factory=list, max_length=11)
    conditions: list[Condition] = Field(default_factory=list)
    max_items: int = Field(default=100, ge=1, le=100)
    score_progress: int = Field(default=0, ge=0, le=1_000_000_000)
    card_level: Literal["BRONZE", "SILVER", "GOLD"] | None = None
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
        if self.mode == "squad" and not self.positions:
            raise ValueError("Les postes du SBC doivent être lus ou fournis.")
        if self.mode == "score" and (
            self.positions
            or not any(
                c.metric == "item_score" and c.value > 0 and c.op in {"min", "exact"}
                for c in self.conditions
            )
        ):
            raise ValueError("Un défi à score exige un objectif Item Score, sans formation.")
        if (
            any(c.metric in {"team_rating", "chemistry"} for c in self.conditions)
            and self.mode != "squad"
        ):
            raise ValueError("Note d'équipe et collectif sont réservés aux défis de composition.")
        if any(c.metric == "team_rating" for c in self.conditions) and len(self.positions) != 11:
            raise ValueError("Le calcul de note est actuellement vérifié pour onze emplacements.")
        if any(c.metric == "chemistry" and c.op != "min" for c in self.conditions):
            raise ValueError("Le profil de collectif standard ne valide que des minima.")
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
    club_id: int | None = Field(default=None, gt=0)
    card_level: Literal["BRONZE", "SILVER", "GOLD"] | None = None
    item_score: int | None = Field(default=None, gt=0, le=1_000_000_000)
    chemistry_kind: Literal["standard", "unsupported"] = "unsupported"
    max_quantity: int = Field(default=1, ge=1, le=100)
    is_rare: bool
    owned: bool
    protected: bool = False
    # Valeur sacrifiée si possédée, prix d'achat sinon. Un inconnu reste None.
    value: int | None = Field(default=None, gt=0, le=1_000_000_000)
    source_url: str = Field(min_length=1)
    observed_at: str = Field(min_length=1)

    @model_validator(mode="after")
    def one_owned_copy(self) -> Self:
        if self.owned and self.max_quantity != 1:
            raise ValueError("Un exemplaire possédé a toujours une quantité de un.")
        return self


class Assignment(StrictModel):
    slot: int = Field(ge=0, le=99)
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
