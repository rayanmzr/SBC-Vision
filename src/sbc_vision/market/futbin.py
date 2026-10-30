"""Lecture des pages et du JSON public utilisés par FUTBIN."""

import re
import time
from datetime import UTC, datetime
from urllib.parse import parse_qs, urlsplit

import httpx
from bs4 import BeautifulSoup

BASE_URL = "https://www.futbin.com"
ATTRIBUTION = f"Données de prix : FUTBIN — {BASE_URL}/"


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

    def page(self, number: int) -> tuple[list[int], int]:
        html = self.get("/27/players", {"page": number}).text
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
        "card_level": raw["cardLevel"],
        "untradeable": raw["untradeable"],
        "stats": raw["playerStats"],
        "prices": prices,
        "source_url": BASE_URL + raw["playerLocation"]["url"],
        "observed_at": observed_at,
    }
