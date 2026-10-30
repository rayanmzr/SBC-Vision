"""Petit stockage SQLite : index des pages, cartes et historique des prix."""

import json
import sqlite3
from pathlib import Path


def open_database(path: str | Path) -> sqlite3.Connection:
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    db = sqlite3.connect(path)
    db.row_factory = sqlite3.Row  # Permet de lire une colonne par son nom.
    db.execute("PRAGMA foreign_keys = ON")
    db.executescript("""
        CREATE TABLE IF NOT EXISTS pages (
            number INTEGER PRIMARY KEY, ids TEXT NOT NULL, last_page INTEGER NOT NULL
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
    return db


def save_page(db: sqlite3.Connection, number: int, ids: list[int], last_page: int):
    # Ce point de reprise permet de retrouver les cartes même si le téléchargement échoue.
    with db:
        db.execute(
            "INSERT OR REPLACE INTO pages VALUES (?, ?, ?)",
            (number, json.dumps(ids), last_page),
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
