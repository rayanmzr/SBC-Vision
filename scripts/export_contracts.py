"""Générer les schémas JSON ou vérifier qu'ils correspondent aux modèles Python."""

import argparse
import json
from pathlib import Path

from sbc_vision.contracts.perception import PerceptionResponse

ROOT = Path(__file__).resolve().parents[1]


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    target = ROOT / "contracts" / "perception.schema.json"
    schema = PerceptionResponse.model_json_schema()
    if args.check:
        if not target.exists() or json.loads(target.read_text()) != schema:
            raise SystemExit("Contrat périmé : exécuter python scripts/export_contracts.py")
        print("Contrats à jour.")
        return
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(schema, ensure_ascii=False, indent=2) + "\n")
    print(target.relative_to(ROOT))


if __name__ == "__main__":
    main()
