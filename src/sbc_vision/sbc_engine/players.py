"""Cartes : catalogue FUTBIN, prix SQLite et exemplaires du club."""

import json
import re
import sqlite3
import time
import unicodedata
from datetime import UTC, datetime, timedelta
from pathlib import Path
from urllib.parse import parse_qs, urlsplit

import httpx
from bs4 import BeautifulSoup

from .models import Candidate, CardReading, ClubItem

BASE_URL = "https://www.futbin.com"
ATTRIBUTION = f"Données de prix : FUTBIN — {BASE_URL}/"


def nested(data, *path):
    for key in path:
        if not isinstance(data, dict):
            return None
        data = data.get(key)
    return data


def import_file(db, path):
    """Lire un export normalisé autorisé, en conservant les dates et les prix inconnus."""
    payload = json.loads(Path(path).read_text())
    cards = payload.get("cards") if isinstance(payload, dict) else None
    if not isinstance(cards, list) or not cards:
        raise ValueError("Le fichier doit contenir une liste non vide nommée cards.")
    if len({c["id"] for c in cards}) != len(cards):
        raise ValueError("Plusieurs lignes portent le même identifiant de version.")
    for card in cards:
        if datetime.fromisoformat(card["observed_at"]).tzinfo is None:
            raise ValueError("Chaque date de collecte doit préciser son fuseau horaire.")
        for market in ("ps", "pc"):
            price = card["prices"].get(market)
            # Le modèle contrôle les types ; les dates ne sont jamais remplacées par aujourd'hui.
            Candidate(
                key="check",
                card_id=card["id"],
                owned=False,
                value=price,
                **{
                    k: card[k]
                    for k in (
                        "base_id",
                        "name",
                        "rating",
                        "positions",
                        "nation_id",
                        "league_id",
                        "is_rare",
                        "source_url",
                        "observed_at",
                    )
                },
            )
        card["prices"] = {m: card["prices"].get(m) for m in ("ps", "pc")}
    old = {
        json.loads(r["data"])["source_url"].startswith("urn:sbc-vision:synthetic:")
        for r in db.execute("SELECT data FROM cards")
    }
    new = {c["source_url"].startswith("urn:sbc-vision:synthetic:") for c in cards}
    if len(old | new) > 1:
        raise ValueError("Conserver les données fictives et réelles dans des bases distinctes.")
    save_cards(db, cards)
    return len(cards)


def open_database(path: str | Path) -> sqlite3.Connection:
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    db = sqlite3.connect(path)
    db.row_factory = sqlite3.Row  # Permet de lire une colonne par son nom.
    db.execute("PRAGMA foreign_keys = ON")
    db.executescript("""
        CREATE TABLE IF NOT EXISTS pages (
            quality TEXT NOT NULL, number INTEGER NOT NULL, ids TEXT NOT NULL,
            last_page INTEGER NOT NULL, PRIMARY KEY(quality, number)
        );
        CREATE TABLE IF NOT EXISTS cards (
            id INTEGER PRIMARY KEY, name TEXT NOT NULL, rating INTEGER NOT NULL,
            data TEXT NOT NULL, observed_at TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS prices (
            card_id INTEGER NOT NULL REFERENCES cards(id), market TEXT NOT NULL,
            credits INTEGER CHECK(credits > 0), observed_at TEXT NOT NULL,
            source_url TEXT NOT NULL, PRIMARY KEY(card_id, market, observed_at),
            CHECK(market IN ('ps', 'pc'))
        );
    """)
    if "quality" not in {row[1] for row in db.execute("PRAGMA table_info(pages)")}:
        # Conserver l'ancien index dans le filtre général, sans toucher aux cartes ni aux prix.
        with db:
            db.execute("BEGIN")
            db.execute("ALTER TABLE pages RENAME TO pages_old")
            db.execute(
                "CREATE TABLE pages (quality TEXT NOT NULL, number INTEGER NOT NULL, "
                "ids TEXT NOT NULL, last_page INTEGER NOT NULL, PRIMARY KEY(quality, number))"
            )
            db.execute("INSERT INTO pages SELECT 'all', number, ids, last_page FROM pages_old")
            db.execute("DROP TABLE pages_old")
    db.execute("""
        CREATE TABLE IF NOT EXISTS club_items (
            instance_id TEXT PRIMARY KEY, card_id INTEGER NOT NULL REFERENCES cards(id),
            protected INTEGER NOT NULL CHECK(protected IN (0, 1)),
            tradeable INTEGER CHECK(tradeable IN (0, 1)),
            source_observation TEXT NOT NULL, last_seen_at TEXT NOT NULL
        )
        """)
    if "item_score" not in {row[1] for row in db.execute("PRAGMA table_info(club_items)")}:
        db.execute("ALTER TABLE club_items ADD COLUMN item_score INTEGER CHECK(item_score > 0)")
    return db


def save_page(db: sqlite3.Connection, number: int, ids: list[int], last_page: int, quality="all"):
    # Ce point de reprise permet de retrouver les cartes même si le téléchargement échoue.
    with db:
        db.execute(
            "INSERT OR REPLACE INTO pages VALUES (?, ?, ?, ?)",
            (quality, number, json.dumps(ids), last_page),
        )


def save_cards(db: sqlite3.Connection, cards: list[dict]):
    # Tout le lot est enregistré ensemble, ou annulé si une écriture échoue.
    with db:
        for card in cards:
            db.execute(
                """INSERT INTO cards VALUES (?, ?, ?, ?, ?)
                   ON CONFLICT(id) DO UPDATE SET name=excluded.name, rating=excluded.rating,
                   data=excluded.data, observed_at=excluded.observed_at""",
                (
                    card["id"],
                    card["name"],
                    card["rating"],
                    json.dumps(card, ensure_ascii=False),
                    card["observed_at"],
                ),
            )
            # On conserve les séries du fournisseur séparément et on date chaque relevé.
            db.executemany(
                "INSERT OR IGNORE INTO prices VALUES (?, ?, ?, ?, ?)",
                [
                    (card["id"], market, price, card["observed_at"], card["source_url"])
                    for market, price in card["prices"].items()
                ],
            )


class Futbin:
    def __init__(self, http: httpx.Client, interval: float = 2):
        self.http = http
        self.interval = max(2, interval)
        self.last_request = 0.0

    def get(self, path: str, params=None) -> httpx.Response:
        # On espace les requêtes, y compris entre deux lots de cartes.
        time.sleep(max(0, self.interval - (time.monotonic() - self.last_request)))
        self.last_request = time.monotonic()
        response = self.http.get(path, params=params)
        response.raise_for_status()  # Un refus HTTP arrête l'import, sans contournement.
        return response

    def page(self, number: int, *, quality="all") -> tuple[list[int], int]:
        if quality not in {"all", "gold", "silver", "bronze"}:
            raise ValueError("Qualité de catalogue inconnue.")
        params = {"page": number}
        if quality != "all":
            params["version"] = quality
        html = self.get("/27/players", params).text
        soup = BeautifulSoup(html, "html.parser")
        ids = []
        for link in soup.select("tr.player-row a.player-row-playercard[href]"):
            match = re.match(r"^/27/player/(\d+)(?:/|$)", link["href"])
            if match:
                ids.append(int(match[1]))
        # Une carte peut apparaître dans les versions mobile et bureau du tableau.
        ids = list(dict.fromkeys(ids))
        if not ids:
            raise ValueError(f"Page {number} sans cartes : le format FUTBIN a peut-être changé.")
        pages = [number]
        for link in soup.select("a.pagination-button[href]"):
            value = parse_qs(urlsplit(link["href"]).query).get("page", [])
            if value and value[0].isdigit():
                pages.append(int(value[0]))
        return ids, max(pages)

    def cards(self, ids: list[int]) -> list[dict]:
        if not 1 <= len(ids) <= 60:
            raise ValueError("Un lot doit contenir entre 1 et 60 identifiants.")
        # Le même paramètre est répété pour demander plusieurs cartes d'un coup.
        response = self.get("/siteapi/27/get-squad", [("playerCardIds", i) for i in ids])
        players = response.json()["squadPlayerData"]
        if set(players) != {str(i) for i in ids}:
            raise ValueError("Lot FUTBIN incomplet : aucune carte de ce lot n'a été enregistrée.")
        observed_at = datetime.now(UTC).isoformat()
        cards = [normalize(players[str(i)], observed_at) for i in ids]
        if [card["id"] for card in cards] != ids:
            raise ValueError("Les identifiants reçus ne correspondent pas aux cartes demandées.")
        return cards


def normalize(raw: dict, observed_at: str) -> dict:
    """Garde les champs utiles, sans les images ni les gros blocs d'affichage."""
    prices = {}
    for market in ("ps", "pc"):
        price = ((raw.get("price") or {}).get(market) or {}).get("price")
        # Un prix nul, absent ou invalide reste inconnu ; il ne vaut pas zéro crédit.
        prices[market] = price if type(price) is int and price > 0 else None
    position = raw["position"]["value"]
    positions = [position] + [item["position"]["value"] for item in raw["possiblePositions"]]
    # Le score doit être explicite et cohérent, jamais déduit de la note seule.
    values = [raw.get("itemScore"), nested(raw, "statsCard", "itemScore")]
    values += [nested(p, "priceBox", "itemScore") for p in (raw.get("price") or {}).values()]
    scores = {v for v in values if type(v) is int and v > 0}
    return {
        "id": raw["id"]["playerCardId"]["value"],
        "base_id": raw["baseId"]["value"],
        "name": raw["statsCard"]["title"],
        "rating": raw["playerRating"],
        "position": position,
        "positions": list(dict.fromkeys(positions)),
        "club_id": raw["clubId"]["value"],
        "league_id": raw["leagueId"]["value"],
        "nation_id": raw["nationId"]["value"],
        "rare_type": raw["rareType"],
        "is_rare": raw["isRare"],
        "chemistry_kind": "standard" if raw["rareType"] in (0, 1) else "unsupported",
        "nation_name": nested(raw, "statsCard", "nationImage", "fixed", "name"),
        "league_name": nested(raw, "statsCard", "leagueImage", "image", "fixed", "name"),
        "club_name": nested(raw, "statsCard", "clubImage", "image", "fixed", "name"),
        "item_score": next(iter(scores)) if len(scores) == 1 else None,
        "card_level": raw["cardLevel"],
        "untradeable": raw["untradeable"],
        "stats": raw["playerStats"],
        "prices": prices,
        "source_url": BASE_URL + raw["playerLocation"]["url"],
        "observed_at": observed_at,
    }


def import_catalog(db, source, pages=2, ids=None, refresh=False, max_age=24, *, quality="all"):
    if quality not in {"all", "gold", "silver", "bronze"} or (ids and quality != "all"):
        raise ValueError("Choisir une qualité valide ; les identifiants ciblés utilisent all.")
    cutoff = (datetime.now(UTC) - timedelta(hours=max_age)).isoformat()
    # Les cartes encore fraîches sont réutilisées plutôt que téléchargées à nouveau.
    fresh = {
        row["id"]
        for row in db.execute(
            "SELECT id FROM cards WHERE observed_at > ? AND "
            "(? = 'all' OR json_extract(data, '$.card_level') = ?)",
            (cutoff, quality, quality.upper()),
        )
    }
    if refresh:
        fresh.clear()
    imported = 0
    previous_ids = None
    for number in range(1, (1 if ids else pages) + 1):
        last_page = number
        if ids:
            page_ids = list(dict.fromkeys(ids))
        else:
            cached = db.execute(
                "SELECT * FROM pages WHERE quality = ? AND number = ?", (quality, number)
            ).fetchone()
            if cached and not refresh:
                page_ids, last_page = json.loads(cached["ids"]), cached["last_page"]
            else:
                page_ids, last_page = source.page(number, quality=quality)
                if page_ids == previous_ids:
                    raise ValueError("FUTBIN répète la même page : import arrêté.")
                save_page(db, number, page_ids, last_page, quality)
            previous_ids = page_ids
        pending = [card_id for card_id in page_ids if card_id not in fresh]
        for start in range(0, len(pending), 60):
            cards = source.cards(pending[start : start + 60])
            if quality != "all" and any(c.get("card_level") != quality.upper() for c in cards):
                raise ValueError("Le lot reçu ne correspond pas à la qualité demandée.")
            save_cards(db, cards)
            fresh.update(card["id"] for card in cards)
            imported += len(cards)
        print(
            f"Page {quality} {number}/{last_page} : {len(pending)} cartes importées, "
            f"{len(page_ids) - len(pending)} en cache."
        )
        if number >= last_page:
            break
    return imported


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
    save_items(db, [item], confirmed=confirmed)


def save_items(db: sqlite3.Connection, items: list[ClubItem], *, confirmed: bool = False):
    if confirmed is not True:
        raise ValueError("Confirmer la version et l'exemplaire avant l'ajout au club.")
    if not items or len({item.instance_id for item in items}) != len(items):
        raise ValueError("Le lot doit contenir des identifiants d'exemplaires distincts.")
    now = datetime.now(UTC).isoformat()
    # Une erreur sur le dernier exemplaire annule aussi les premières écritures du lot.
    with db:
        for item in items:
            existing = db.execute(
                "SELECT card_id FROM club_items WHERE instance_id = ?", (item.instance_id,)
            ).fetchone()
            if existing and existing["card_id"] != item.card_id:
                raise ValueError("Cet identifiant d'exemplaire désigne déjà une autre version.")
            if existing:
                # Revoir une carte ne crée pas un doublon et ne retire pas sa protection.
                db.execute(
                    "UPDATE club_items SET source_observation = ?, last_seen_at = ?, "
                    "item_score = COALESCE(?, item_score) WHERE instance_id = ?",
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


def confirm_readings(db, report, choices, *, confirmed=False):
    """Relier les versions choisies aux exemplaires suivis par le contrôleur."""
    if not isinstance(choices, dict) or not choices:
        raise ValueError("Choisir au moins un élément du rapport OCR.")
    readings = {card["element_id"]: card for card in report["cards"]}
    if len(readings) != len(report["cards"]):
        raise ValueError("Le rapport contient plusieurs lectures du même élément.")
    items = []
    for element_id, choice in choices.items():
        card = readings[element_id]
        reading = CardReading.model_validate(card["reading"])
        if (
            card.get("issues")
            or reading.element_id != element_id
            or reading.capture_id != report["capture_id"]
        ):
            raise ValueError(f"Lecture à corriger avant confirmation : {element_id}.")
        item = ClubItem(
            **choice,
            source_observation=f"{reading.capture_id}:{element_id}",
            item_score=reading.item_score,
        )
        # Recalculer les candidats : une ancienne liste JSON ne prouve pas la correspondance.
        if item.card_id not in {candidate["id"] for candidate in find_candidates(db, reading)}:
            raise ValueError(f"Version incompatible avec la lecture : {element_id}.")
        items.append(item)
    save_items(db, items, confirmed=confirmed)
    return len(items)


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
