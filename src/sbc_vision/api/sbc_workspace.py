"""Adaptateur HTTP du moteur SBC de Rayan, sans capture ni action sur EA."""

import hashlib
import importlib.util
import json
import os
import sqlite3
from contextlib import closing
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from threading import BoundedSemaphore
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, ConfigDict, Field, ValidationError

from sbc_vision.sbc_engine.models import Candidate, Challenge

router = APIRouter(prefix="/api/v1/sbc", tags=["sbc"])
solve_slot = BoundedSemaphore(1)


@dataclass(frozen=True)
class SbcConfig:
    database: Path
    challenge_path: Path | None
    mode: Literal["demo", "local"]


class WorkspaceSnapshot(BaseModel):
    mode: Literal["demo", "local"]
    revision: str
    price_reference_at: str
    items: list[Candidate]
    challenge: Challenge | None
    challenge_issues: list[str]


class ProtectionRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    instance_id: str = Field(min_length=1, max_length=256)
    protected: bool
    expected_revision: str = Field(pattern="^[0-9a-f]{64}$")


class SolveRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    expected_revision: str = Field(pattern="^[0-9a-f]{64}$")
    budget: int | None = Field(default=None, ge=0, le=1_000_000_000)
    max_card_value: int | None = Field(default=None, gt=0, le=1_000_000_000)
    seconds: float = Field(default=3.0, gt=0, le=5)


class SolveResponse(BaseModel):
    mode: Literal["demo", "local"]
    revision: str
    report: dict


def fail(status: int, code: str, message: str) -> HTTPException:
    return HTTPException(status_code=status, detail={"code": code, "message": message})


def get_sbc_config() -> SbcConfig | None:
    mode, database = os.getenv("SBC_ENGINE_MODE"), os.getenv("SBC_ENGINE_DATABASE")
    if mode not in {"demo", "local"} or not database:
        return None
    challenge = os.getenv("SBC_ENGINE_CHALLENGE")
    return SbcConfig(
        database=Path(database).expanduser().resolve(),
        challenge_path=Path(challenge).expanduser().resolve() if challenge else None,
        mode=mode,
    )


def sbc_available(config: SbcConfig | None) -> bool:
    return bool(
        config
        and config.database.is_file()
        and all(importlib.util.find_spec(name) for name in ("httpx", "bs4", "ortools"))
    )


class SbcWorkspace:
    def __init__(self, config: SbcConfig):
        if not sbc_available(config):
            raise fail(
                503, "sbc_unavailable", "Configurer la base et installer les options data,solver."
            )
        from sbc_vision.sbc_engine import players, solver

        self.config, self.players, self.solver = config, players, solver

    def challenge_document(self) -> tuple[dict, Challenge | None, list[str]]:
        path = self.config.challenge_path
        if path is None or not path.is_file():
            return {}, None, ["Aucun fichier de conditions n'est configuré."]
        try:
            if path.stat().st_size > 2 * 1024 * 1024:
                raise ValueError("size")
            document = json.loads(path.read_text())
            if not isinstance(document, dict):
                raise ValueError("object expected")
            if document.get("ready") is False:
                return document, None, ["Les conditions OCR doivent être confirmées."]
            challenge = Challenge.model_validate(document.get("challenge", document))
            return document, challenge, []
        except (OSError, ValueError, ValidationError) as exc:
            raise fail(
                503, "invalid_sbc_configuration", "Le fichier de conditions est invalide."
            ) from exc

    def reference_time(self, document: dict) -> datetime:
        if self.config.mode == "local":
            return datetime.now(UTC)
        try:
            if document.get("data_kind") != "synthetic":
                raise ValueError("synthetic marker missing")
            reference = datetime.fromisoformat(document["price_reference_at"])
            if reference.tzinfo is None:
                raise ValueError("timezone missing")
            return reference
        except (ValueError, KeyError, TypeError) as exc:
            raise fail(
                503,
                "invalid_demo",
                "La démo exige des conditions et une date fictives identifiées.",
            ) from exc

    def read_state(self, db, document, challenge, reference):
        cards = [
            dict(row) for row in db.execute("SELECT id,data,observed_at FROM cards ORDER BY id")
        ]
        items = self.players.list_items(db)
        synthetic = [
            json.loads(card["data"])["source_url"].startswith("urn:sbc-vision:synthetic:")
            for card in cards
        ]
        if (self.config.mode == "demo" and (not synthetic or not all(synthetic))) or (
            self.config.mode == "local" and any(synthetic)
        ):
            raise fail(
                503,
                "data_mode_mismatch",
                "La provenance de la base ne correspond pas au mode configuré.",
            )
        pool = self.players.load_pool(db, challenge.market if challenge else "pc", now=reference)
        # La péremption d'un prix change aussi la révision, sans recopier les règles du moteur.
        serialized = json.dumps(
            {
                "cards": cards,
                "items": items,
                "challenge": document,
                "values": [(card.key, card.value) for card in pool],
            },
            sort_keys=True,
        )
        return hashlib.sha256(serialized.encode()).hexdigest(), pool

    @staticmethod
    def require_revision(actual: str, expected: str):
        if actual != expected:
            raise fail(
                409,
                "workspace_changed",
                "L'inventaire, les prix ou les conditions ont changé. Recharger et recalculer.",
            )

    def snapshot(self) -> WorkspaceSnapshot:
        document, challenge, issues = self.challenge_document()
        reference = self.reference_time(document)
        with closing(self.players.open_database(self.config.database)) as db:
            db.execute("BEGIN")
            revision, pool = self.read_state(db, document, challenge, reference)
        return WorkspaceSnapshot(
            mode=self.config.mode,
            revision=revision,
            price_reference_at=reference.isoformat(),
            items=[card for card in pool if card.owned],
            challenge=challenge,
            challenge_issues=issues,
        )

    def protect(self, request: ProtectionRequest) -> WorkspaceSnapshot:
        document, challenge, _ = self.challenge_document()
        reference = self.reference_time(document)
        with closing(self.players.open_database(self.config.database)) as db:
            db.execute("BEGIN IMMEDIATE")
            revision, _ = self.read_state(db, document, challenge, reference)
            self.require_revision(revision, request.expected_revision)
            if not db.execute(
                "SELECT 1 FROM club_items WHERE instance_id=?", (request.instance_id,)
            ).fetchone():
                raise fail(
                    404, "item_not_found", "Cet exemplaire n'est pas présent dans l'inventaire."
                )
            self.players.set_protected(db, request.instance_id, request.protected)
        return self.snapshot()

    def solve(self, request: SolveRequest) -> SolveResponse:
        if not solve_slot.acquire(blocking=False):
            raise fail(429, "solver_busy", "Un calcul est déjà en cours. Réessayer après sa fin.")
        try:
            document, challenge, _ = self.challenge_document()
            if challenge is None:
                raise fail(
                    409,
                    "challenge_uncertain",
                    "Les conditions du SBC doivent être relues avant le calcul.",
                )
            preferences = {
                key: getattr(request, key)
                for key in ("budget", "max_card_value")
                if getattr(request, key) is not None
            }
            challenge = Challenge.model_validate({**challenge.model_dump(), **preferences})
            reference = self.reference_time(document)
            with closing(self.players.open_database(self.config.database)) as db:
                db.execute("BEGIN")
                revision, pool = self.read_state(db, document, challenge, reference)
                self.require_revision(revision, request.expected_revision)
            outcome = self.solver.solve(challenge, pool, seconds=request.seconds)
            report = {
                "challenge": challenge.model_dump(),
                "price_reference_at": reference.isoformat(),
                "solution": outcome.model_dump(),
                "selected_candidates": [
                    card.model_dump()
                    for card in pool
                    if card.key in {a.candidate_key for a in outcome.assignments}
                ],
                "verification": self.solver.verification(challenge, pool, outcome),
                "shopping_list": self.solver.shopping_list(challenge, pool, outcome),
                "data_kind": "synthetic" if self.config.mode == "demo" else "local",
            }
            latest_document, latest_challenge, _ = self.challenge_document()
            latest_reference = self.reference_time(latest_document)
            with closing(self.players.open_database(self.config.database)) as db:
                db.execute("BEGIN")
                latest_revision, current = self.read_state(
                    db, latest_document, latest_challenge, latest_reference
                )
                self.require_revision(latest_revision, revision)
            if (
                outcome.status in {"optimal", "feasible"}
                and not self.solver.recheck(report, current)["valid"]
            ):
                raise fail(
                    409,
                    "proposal_expired",
                    "Les données de la proposition ont expiré pendant le calcul.",
                )
            return SolveResponse(mode=self.config.mode, revision=revision, report=report)
        finally:
            solve_slot.release()


def get_workspace(config: Annotated[SbcConfig | None, Depends(get_sbc_config)]) -> SbcWorkspace:
    if config is None:
        raise fail(503, "sbc_unavailable", "L'espace SBC n'est pas configuré sur ce serveur.")
    return SbcWorkspace(config)


def database_call(operation, *args):
    try:
        return operation(*args)
    except sqlite3.Error as exc:
        raise fail(
            503,
            "inventory_unavailable",
            "L'inventaire local est indisponible. Réessayer après vérification du serveur.",
        ) from exc
    except (ValueError, KeyError, TypeError) as exc:
        raise fail(
            503,
            "invalid_workspace_data",
            "Les données locales doivent être vérifiées avant de continuer.",
        ) from exc


@router.get("/workspace", response_model=WorkspaceSnapshot)
def workspace_snapshot(service: Annotated[SbcWorkspace, Depends(get_workspace)]):
    """Lire l'inventaire confirmé, sa révision et les conditions configurées sur le serveur."""
    return database_call(service.snapshot)


@router.put("/protections", response_model=WorkspaceSnapshot)
def update_protection(
    body: ProtectionRequest, service: Annotated[SbcWorkspace, Depends(get_workspace)]
):
    """Enregistrer une protection si les données correspondent toujours à la révision affichée."""
    return database_call(service.protect, body)


@router.post("/solve", response_model=SolveResponse)
def solve_workspace(body: SolveRequest, service: Annotated[SbcWorkspace, Depends(get_workspace)]):
    """Appeler le vrai solveur CP-SAT ; le corps contient uniquement du JSON."""
    return database_call(service.solve, body)
