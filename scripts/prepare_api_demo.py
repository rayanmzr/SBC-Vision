"""Préparer un inventaire et des conditions fictifs pour l'API, sans réseau ni OCR."""

import argparse
import json
from contextlib import closing
from pathlib import Path

from sbc_vision.sbc_engine.players import open_database, seed_demo


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--directory", type=Path, default=Path("data/processed/api_demo"))
    args = parser.parse_args()
    args.directory.mkdir(parents=True, exist_ok=True)
    challenge_path = args.directory / "challenge.json"
    if (
        challenge_path.exists()
        and json.loads(challenge_path.read_text()).get("data_kind") != "synthetic"
    ):
        raise ValueError(
            "Ce dossier contient des conditions non fictives ; choisir un autre dossier."
        )
    fixtures = Path(__file__).resolve().parents[1] / "data/fixtures"
    club = json.loads((fixtures / "club.synthetic.json").read_text())
    solver = json.loads((fixtures / "solver.synthetic.json").read_text())
    database = args.directory / "inventory.sqlite3"
    with closing(open_database(database)) as db:
        seed_demo(db, club, solver["extra_cards"])
    challenge_path.write_text(
        json.dumps(
            {
                "data_kind": "synthetic",
                "price_reference_at": solver["price_reference_at"],
                "challenge": {**solver["challenge"], "max_card_value": 1000},
            },
            ensure_ascii=False,
            indent=2,
        )
        + "\n"
    )
    print(f"Démo fictive prête : {database} ; {challenge_path}.")
    print("Configurer SBC_ENGINE_MODE=demo, SBC_ENGINE_DATABASE et SBC_ENGINE_CHALLENGE.")


if __name__ == "__main__":
    main()
