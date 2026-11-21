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
from time import monotonic
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, ConfigDict, Field, ValidationError

from sbc_vision.contracts.ocr import OcrAnalysisResponse
from sbc_vision.sbc_engine.models import Candidate, CardObservation, Challenge

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
    protection_policy: Literal["preserve", "active_squad"] = "preserve"
    active_squad_keys: list[str] = Field(default_factory=list)


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
    seconds: float = Field(default=3.0, gt=0, le=30)
    prefer_club: bool = False
    challenge: Challenge | None = None


class SbcReadingRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    source: Literal["dom"]
    requirements: str = Field(min_length=1, max_length=16000)
    positions: list[str] = Field(min_length=1, max_length=11)
    market: Literal["pc", "ps"] = "pc"
    budget: int = Field(ge=0, le=1_000_000_000)


class InventoryChoice(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    instance_id: str = Field(min_length=1, max_length=256)
    card_id: int = Field(gt=0)
    protected: bool = True


class InventoryRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    expected_revision: str = Field(pattern="^[0-9a-f]{64}$")
    report: OcrAnalysisResponse
    choices: dict[str, InventoryChoice]
    confirmed: Literal[True]


class DomCard(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    reading: CardObservation
    visible: bool
    loan: bool
    active: bool | None = None
    rarity: str | None = Field(default=None, max_length=100)


class ClubPage(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    cards: list[DomCard] = Field(min_length=1, max_length=100)
    has_previous: bool
    has_next: bool
    ocr: OcrAnalysisResponse | None = None
    ocr_error: str | None = Field(default=None, max_length=500)


class ClubScanRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    capture_id: str = Field(min_length=1, max_length=128)
    pages: list[ClubPage] = Field(min_length=1, max_length=500)
    complete: bool
    confirmed: bool = False
    protection_policy: Literal["preserve", "active_squad"] = "preserve"
    expected_revision: str = Field(pattern="^[0-9a-f]{64}$")


class PlacementCard(BaseModel):
    slot: int = Field(ge=0, le=10)
    candidate_key: str
    card_id: int = Field(gt=0)
    reading: CardObservation


class PlacementPlan(BaseModel):
    cards: list[PlacementCard] = Field(max_length=11)
    issues: list[str]


class SolveResponse(BaseModel):
    mode: Literal["demo", "local"]
    revision: str
    report: dict
    placement: PlacementPlan | None = None


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
                "scan": self.scan_document(db),
            },
            sort_keys=True,
        )
        return hashlib.sha256(serialized.encode()).hexdigest(), pool

    @staticmethod
    def scan_document(db):
        exists = db.execute("SELECT 1 FROM sqlite_master WHERE name='club_scans'").fetchone()
        row = (
            db.execute("SELECT data FROM club_scans ORDER BY rowid DESC LIMIT 1").fetchone()
            if exists
            else None
        )
        return json.loads(row[0]) if row else None

    def placement_plan(self, db, report):
        """Fournir les empreintes du dernier scan, jamais une autorisation d'échange."""
        if report["solution"]["status"] not in {"optimal", "feasible"}:
            return None
        if report["challenge"]["mode"] != "squad":
            return {
                "cards": [],
                "issues": ["Le placement prend uniquement en charge une composition d'équipe."],
            }
        issues, cards = [], []
        selected = {c["key"]: c for c in report["selected_candidates"]}
        scan = self.scan_document(db)
        if self.config.mode != "local" or not scan or not scan["report"]["inventory_updated"]:
            return {
                "cards": [],
                "issues": ["Scanner et confirmer le club réel avant le placement."],
            }
        observed = scan["report"]["cards"]
        for assignment in report["solution"]["assignments"]:
            candidate = selected[assignment["candidate_key"]]
            if not candidate["owned"]:
                issues.append(f"À acheter manuellement : {candidate['name']}.")
                continue
            item = db.execute(
                "SELECT * FROM club_items WHERE instance_id=?", (candidate["key"][5:],)
            ).fetchone()
            copies = db.execute(
                "SELECT COUNT(*) FROM club_items WHERE card_id=?", (candidate["card_id"],)
            ).fetchone()[0]
            match = [
                c
                for c in observed
                if item
                and item["source_observation"]
                == f"dom:{scan['observation']['capture_id']}:{c['reading']['element_id']}"
            ]
            reading = match[0]["reading"] if len(match) == 1 else None
            if (
                not item
                or item["protected"]
                or (match and match[0].get("active"))
                or copies != 1
                or not reading
                or match[0]["loan"]
                or match[0]["candidate_ids"] != [candidate["card_id"]]
                or len(reading.get("stats", {})) != 6
                or not all(
                    reading.get(k) for k in ("position", "nation_id", "league_id", "club_id")
                )
                or [
                    c["id"]
                    for c in self.players.find_candidates(
                        db, CardObservation.model_validate(reading)
                    )
                ]
                != [candidate["card_id"]]
            ):
                issues.append(f"Exemplaire à vérifier : {candidate['name']}.")
                continue
            cards.append({**assignment, "card_id": candidate["card_id"], "reading": reading})
        # Un plan partiel ne démarre jamais un remplissage partiel silencieux.
        return {"cards": [] if issues else cards, "issues": issues}

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
            scan = self.scan_document(db)
        active_versions = {
            version
            for c in (scan or {}).get("report", {}).get("cards", [])
            if c.get("active")
            for version in c["candidate_ids"]
        }
        return WorkspaceSnapshot(
            mode=self.config.mode,
            revision=revision,
            price_reference_at=reference.isoformat(),
            items=[card for card in pool if card.owned],
            challenge=challenge,
            challenge_issues=issues,
            protection_policy=(scan or {}).get("report", {}).get("protection_policy", "preserve"),
            active_squad_keys=[c.key for c in pool if c.owned and c.card_id in active_versions],
        )

    def protect(self, request: ProtectionRequest) -> WorkspaceSnapshot:
        document, challenge, _ = self.challenge_document()
        reference = self.reference_time(document)
        with closing(self.players.open_database(self.config.database)) as db:
            db.execute("BEGIN IMMEDIATE")
            revision, _ = self.read_state(db, document, challenge, reference)
            self.require_revision(revision, request.expected_revision)
            scan = self.scan_document(db)
            active_versions = {
                version
                for c in (scan or {}).get("report", {}).get("cards", [])
                if c.get("active")
                for version in c["candidate_ids"]
            }
            item = db.execute(
                "SELECT card_id FROM club_items WHERE instance_id=?", (request.instance_id,)
            ).fetchone()
            if not request.protected and item and item["card_id"] in active_versions:
                raise fail(
                    409,
                    "active_squad_card",
                    "Ce joueur appartient à ton équipe active ; il reste protégé.",
                )
            if not db.execute(
                "SELECT 1 FROM club_items WHERE instance_id=?", (request.instance_id,)
            ).fetchone():
                raise fail(
                    404, "item_not_found", "Cet exemplaire n'est pas présent dans l'inventaire."
                )
            self.players.set_protected(db, request.instance_id, request.protected)
        return self.snapshot()

    def record(self, request: InventoryRequest) -> WorkspaceSnapshot:
        document, challenge, _ = self.challenge_document()
        reference = self.reference_time(document)
        with closing(self.players.open_database(self.config.database)) as db:
            db.execute("BEGIN IMMEDIATE")
            revision, _ = self.read_state(db, document, challenge, reference)
            self.require_revision(revision, request.expected_revision)
            try:
                self.players.confirm_readings(
                    db,
                    request.report.model_dump(),
                    {k: v.model_dump() for k, v in request.choices.items()},
                    confirmed=True,
                )
            except (ValueError, KeyError, TypeError) as exc:
                raise fail(
                    422,
                    "invalid_inventory_choice",
                    "Relire la carte, sa version et son identifiant d'exemplaire.",
                ) from exc
        return self.snapshot()

    def solve(self, request: SolveRequest) -> SolveResponse:
        if not solve_slot.acquire(blocking=False):
            raise fail(429, "solver_busy", "Un calcul est déjà en cours. Réessayer après sa fin.")
        try:
            document, configured, _ = self.challenge_document()
            challenge = request.challenge or configured
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
                revision, _ = self.read_state(db, document, configured, reference)
                self.require_revision(revision, request.expected_revision)
                pool = self.players.load_pool(db, challenge.market, now=reference)
            started = monotonic()
            # Chercher d'abord un remplissage sans achat, sous les mêmes limites de valeur.
            club = [c for c in pool if c.owned and not c.protected]
            outcome = (
                self.solver.solve(
                    challenge, club, seconds=request.seconds / 2, prefer_low_rating=True
                )
                if request.prefer_club and club
                else None
            )
            club_only = outcome is not None and outcome.status in {"optimal", "feasible"}
            if not club_only:
                outcome = self.solver.solve(
                    challenge, pool, seconds=max(0.001, request.seconds - (monotonic() - started))
                )
            outcome = outcome.model_copy(update={"elapsed_seconds": monotonic() - started})
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
                "selection_scope": "club" if club_only else "club_and_market",
                "selection_priority": "rating_then_value"
                if club_only and challenge.position_mode == "any"
                else "value",
            }
            latest_document, latest_challenge, _ = self.challenge_document()
            latest_reference = self.reference_time(latest_document)
            with closing(self.players.open_database(self.config.database)) as db:
                db.execute("BEGIN")
                latest_revision, current = self.read_state(
                    db, latest_document, latest_challenge, latest_reference
                )
                self.require_revision(latest_revision, revision)
                current = self.players.load_pool(db, challenge.market, now=latest_reference)
                placement = self.placement_plan(db, report)
            if (
                outcome.status in {"optimal", "feasible"}
                and not self.solver.recheck(report, current)["valid"]
            ):
                raise fail(
                    409,
                    "proposal_expired",
                    "Les données de la proposition ont expiré pendant le calcul.",
                )
            return SolveResponse(
                mode=self.config.mode, revision=revision, report=report, placement=placement
            )
        finally:
            solve_slot.release()

    def record_scan(self, request: ClubScanRequest) -> dict:
        if self.config.mode != "local":
            raise fail(409, "local_inventory_required", "Le scan EA exige une base en mode local.")
        document, challenge, _ = self.challenge_document()
        with closing(self.players.open_database(self.config.database)) as db:
            db.execute("BEGIN IMMEDIATE")
            revision, _ = self.read_state(db, document, challenge, self.reference_time(document))
            self.require_revision(revision, request.expected_revision)
            try:
                report = self.players.save_dom_scan(
                    db,
                    request.model_dump(exclude={"expected_revision", "confirmed"}),
                    confirmed=request.confirmed,
                )
            except ValueError as exc:
                raise fail(422, "invalid_club_scan", str(exc)) from exc
        return {**report, "expected_revision": self.snapshot().revision}

    def latest_scan(self) -> dict:
        revision = self.snapshot().revision
        with closing(self.players.open_database(self.config.database)) as db:
            exists = db.execute("SELECT 1 FROM sqlite_master WHERE name='club_scans'").fetchone()
            row = (
                db.execute("SELECT data FROM club_scans ORDER BY rowid DESC LIMIT 1").fetchone()
                if exists
                else None
            )
        if not row:
            raise fail(404, "club_scan_missing", "Aucun relevé du club n'est enregistré.")
        return {**json.loads(row[0]), "expected_revision": revision}


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


@router.post("/read")
def read_sbc(body: SbcReadingRequest, service: Annotated[SbcWorkspace, Depends(get_workspace)]):
    """Interpréter le texte courant du DOM, sans lui attribuer une confiance OCR."""
    from sbc_vision.sbc_engine.ocr import parse_requirements

    with closing(service.players.open_database(service.config.database)) as db:
        return {
            "source": "dom",
            **parse_requirements(
                body.requirements,
                db,
                positions=body.positions,
                market=body.market,
                budget=body.budget,
            ),
        }


@router.post("/inventory", response_model=WorkspaceSnapshot)
def record_readings(
    body: InventoryRequest, service: Annotated[SbcWorkspace, Depends(get_workspace)]
):
    """Enregistrer les versions et exemplaires explicitement confirmés ; aucun clic EA."""
    return database_call(service.record, body)


@router.post("/club-scan")
def record_club_scan(
    body: ClubScanRequest, service: Annotated[SbcWorkspace, Depends(get_workspace)]
):
    """Sauver le scan hybride ; la confirmation remplace seulement le comptage local DOM."""
    return database_call(service.record_scan, body)


@router.get("/club-scan")
def latest_club_scan(service: Annotated[SbcWorkspace, Depends(get_workspace)]):
    """Rouvrir le dernier relevé privé après fermeture du popup."""
    return database_call(service.latest_scan)
