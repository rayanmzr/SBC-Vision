"""Lancement : python -m sbc_vision.market --pages 2."""

import argparse
import json
import os
import sqlite3
from contextlib import closing
from datetime import UTC, datetime, timedelta

import httpx

from sbc_vision.market.database import open_database, save_cards, save_page
from sbc_vision.market.futbin import ATTRIBUTION, BASE_URL, Futbin


def import_catalog(db, source, pages=2, ids=None, refresh=False, max_age=24):
    cutoff = (datetime.now(UTC) - timedelta(hours=max_age)).isoformat()
    # Les cartes encore fraîches sont réutilisées plutôt que téléchargées à nouveau.
    fresh = {
        row["id"] for row in db.execute("SELECT id FROM cards WHERE observed_at > ?", (cutoff,))
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
            cached = db.execute("SELECT * FROM pages WHERE number = ?", (number,)).fetchone()
            if cached and not refresh:
                page_ids, last_page = json.loads(cached["ids"]), cached["last_page"]
            else:
                page_ids, last_page = source.page(number)
                if page_ids == previous_ids:
                    raise ValueError("FUTBIN répète la même page : import arrêté.")
                save_page(db, number, page_ids, last_page)
            previous_ids = page_ids
        pending = [card_id for card_id in page_ids if card_id not in fresh]
        for start in range(0, len(pending), 60):
            cards = source.cards(pending[start : start + 60])
            save_cards(db, cards)
            fresh.update(card["id"] for card in cards)
            imported += len(cards)
        print(
            f"Page {number}/{last_page} : {len(pending)} cartes importées, "
            f"{len(page_ids) - len(pending)} en cache."
        )
        if number >= last_page:
            break
    return imported


def main() -> int:
    parser = argparse.ArgumentParser(description="Importer le catalogue FUTBIN FC 27 dans SQLite.")
    parser.add_argument(
        "--pages", type=int, default=2, help="Nombre maximal de pages (défaut : 2)."
    )
    parser.add_argument(
        "--ids", nargs="+", type=int, help="Importer seulement ces versions de cartes."
    )
    parser.add_argument("--db", default="data/processed/futbin_fc27.sqlite3")
    parser.add_argument(
        "--refresh", action="store_true", help="Relire les pages et les prix en cache."
    )
    parser.add_argument(
        "--max-age", type=float, default=24, help="Durée du cache des cartes en heures."
    )
    args = parser.parse_args()
    if args.pages < 1 or args.max_age < 0 or (args.ids and min(args.ids) < 1):
        parser.error(
            "Pages et identifiants doivent être positifs ; max-age doit être positif ou nul."
        )
    try:
        # gzip réduit le volume ; une seule connexion HTTP est réutilisée pendant l'import.
        with (
            closing(open_database(args.db)) as db,
            httpx.Client(
                base_url=BASE_URL,
                timeout=30,
                follow_redirects=True,
                headers={
                    "User-Agent": "SBC-Vision/0.1 (projet etudiant)",
                    "Accept-Encoding": "gzip",
                },
            ) as http,
        ):
            source = Futbin(http, float(os.getenv("FUTBIN_MIN_INTERVAL_SECONDS", "2")))
            count = import_catalog(db, source, args.pages, args.ids, args.refresh, args.max_age)
            total = db.execute("SELECT COUNT(*) FROM cards").fetchone()[0]
            print(f"{count} cartes téléchargées ; {total} versions en base : {args.db}")
            print(ATTRIBUTION)
    except (httpx.HTTPError, ValueError, KeyError, TypeError, sqlite3.Error) as error:
        print(f"Import arrêté : {error}. Les lots enregistrés sont conservés. Relance la commande.")
        return 1
    except KeyboardInterrupt:
        print("Import interrompu. Les lots enregistrés sont conservés pour la reprise.")
        return 130
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
