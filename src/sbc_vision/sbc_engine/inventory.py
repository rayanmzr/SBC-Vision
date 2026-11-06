"""Exemplaires du club, rapprochement et candidats du solveur."""

import json
import sqlite3
import unicodedata
from datetime import UTC, datetime, timedelta

from .catalogue import save_cards
from .models import Candidate, CardReading, ClubItem


def normalize_name(name: str) -> str:
    # « José Test » et « jose-test » se comparent sans accents ni ponctuation.
    return "".join(c for c in unicodedata.normalize("NFKD", name.casefold()) if c.isalnum())


def find_candidates(db: sqlite3.Connection, reading: CardReading) -> list[dict]:
    filters = {
        key: getattr(reading, key)
        for key in ("club_id", "league_id", "nation_id", "rare_type", "is_rare")
    }
    candidates = []
    for row in db.execute("SELECT data FROM cards WHERE rating = ? ORDER BY id", (reading.rating,)):
        card = json.loads(row["data"])
        if normalize_name(card["name"]) != normalize_name(reading.name):
            continue
        if reading.position and reading.position not in card["positions"]:
            continue
        if any(value is not None and card.get(key) != value for key, value in filters.items()):
            continue
        candidates.append(card)
    # Même un seul candidat reste à confirmer : le catalogue peut être incomplet.
    return candidates


def save_item(db: sqlite3.Connection, item: ClubItem, *, confirmed: bool = False):
    if confirmed is not True:
        raise ValueError("Confirmer la version et l'exemplaire avant l'ajout au club.")
    now = datetime.now(UTC).isoformat()
    with db:
        existing = db.execute(
            "SELECT card_id FROM club_items WHERE instance_id = ?", (item.instance_id,)
        ).fetchone()
        if existing and existing["card_id"] != item.card_id:
            raise ValueError("Cet identifiant d'exemplaire désigne déjà une autre version.")
        if existing:
            # Revoir une carte ne crée pas un doublon et ne retire pas sa protection.
            db.execute(
                "UPDATE club_items SET source_observation = ?, last_seen_at = ?, "
                "item_score = COALESCE(?, item_score) "
                "WHERE instance_id = ?",
                (item.source_observation, now, item.item_score, item.instance_id),
            )
        else:
            db.execute(
                "INSERT INTO club_items VALUES (?, ?, ?, ?, ?, ?, ?)",
                (
                    item.instance_id,
                    item.card_id,
                    item.protected,
                    item.tradeable,
                    item.source_observation,
                    now,
                    item.item_score,
                ),
            )


def set_protected(db: sqlite3.Connection, instance_id: str, protected: bool):
    if type(protected) is not bool:
        raise ValueError("La protection doit être un booléen.")
    with db:
        result = db.execute(
            "UPDATE club_items SET protected = ? WHERE instance_id = ?", (protected, instance_id)
        )
        if result.rowcount == 0:
            raise ValueError("Exemplaire introuvable dans le club.")


def list_items(db: sqlite3.Connection, *, unprotected_only: bool = False) -> list[dict]:
    rows = db.execute(
        """SELECT i.*, c.name, c.rating FROM club_items i JOIN cards c ON c.id = i.card_id
           WHERE (? = 0 OR i.protected = 0) ORDER BY i.card_id, i.instance_id""",
        (unprotected_only,),
    )
    items = [dict(row) for row in rows]
    for item in items:
        item["protected"] = bool(item["protected"])
        if item["tradeable"] is not None:
            item["tradeable"] = bool(item["tradeable"])
    return items


def load_pool(db, market, *, now=None, max_age_hours=24) -> list[Candidate]:
    now = now or datetime.now(UTC)
    if market not in ("ps", "pc") or max_age_hours <= 0:
        raise ValueError("Choisir une série ps/pc et une durée de validité positive.")
    cards = {row["id"]: json.loads(row["data"]) for row in db.execute("SELECT id, data FROM cards")}
    pool = []

    def add(card, key, owned, protected=False, score=None):
        observed = datetime.fromisoformat(card["observed_at"])
        if observed.tzinfo is None:
            raise ValueError("La date de collecte doit inclure son fuseau horaire.")
        value = card["prices"].get(market)
        # Les prix trop vieux, futurs, absents ou nuls ne deviennent pas des coûts gratuits.
        if not now - timedelta(hours=max_age_hours) <= observed <= now:
            value = None
        if type(value) is not int or value <= 0:
            value = None
        pool.append(
            Candidate(
                key=key,
                card_id=card["id"],
                base_id=card["base_id"],
                name=card["name"],
                rating=card["rating"],
                positions=card["positions"],
                nation_id=card["nation_id"],
                league_id=card["league_id"],
                club_id=card.get("club_id"),
                card_level=card.get("card_level"),
                item_score=score if score is not None else card.get("item_score"),
                chemistry_kind=card.get("chemistry_kind", "unsupported"),
                max_quantity=1 if owned else card.get("market_quantity", 1),
                is_rare=card["is_rare"],
                owned=owned,
                protected=protected,
                value=value,
                source_url=card["source_url"],
                observed_at=card["observed_at"],
            )
        )

    for item in list_items(db):
        add(
            cards[item["card_id"]],
            f"club:{item['instance_id']}",
            True,
            item["protected"],
            item["item_score"],
        )
    for card in cards.values():
        # Un statut non échangeable dans le catalogue n'est pas une offre d'achat.
        if not card.get("untradeable", False):
            add(card, f"market:{card['id']}", False)
    return pool


def seed_demo(db, club, extra_cards):
    if any(
        not json.loads(row["data"])["source_url"].startswith("urn:sbc-vision:synthetic:")
        for row in db.execute("SELECT data FROM cards")
    ):
        raise ValueError("La démo nécessite une base sans données réelles.")
    save_cards(db, club["catalogue"] + extra_cards)
    for item in club["items"]:
        save_item(db, ClubItem.model_validate(item), confirmed=True)
