"""Générer les schémas JSON ou vérifier qu'ils correspondent aux modèles Python."""

import argparse
import json
from pathlib import Path

from sbc_vision.contracts.perception import PerceptionResponse
from sbc_vision.sbc_engine.models import CardReading, Challenge, ClubItem, SolverResult

ROOT = Path(__file__).resolve().parents[1]


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    models = {
        "perception": PerceptionResponse,
        "card-reading": CardReading,
        "club-item": ClubItem,
        "challenge": Challenge,
        "solver-result": SolverResult,
    }
    for name, model in models.items():
        target = ROOT / "contracts" / f"{name}.schema.json"
        schema = model.model_json_schema()
        if args.check:
            if not target.exists() or json.loads(target.read_text()) != schema:
                raise SystemExit(f"Contrat périmé : {name}. Exécuter scripts/export_contracts.py")
        else:
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(json.dumps(schema, ensure_ascii=False, indent=2) + "\n")
            print(target.relative_to(ROOT))
    if args.check:
        print("Contrats à jour.")


if __name__ == "__main__":
    main()
