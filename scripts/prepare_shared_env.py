"""Créer une clé locale pour Compose, sans l'afficher ni remplacer une clé existante."""

import argparse
import os
import secrets
from pathlib import Path


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--file", type=Path, default=Path(".env.shared"))
    args = parser.parse_args()
    try:
        descriptor = os.open(args.file, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    except FileExistsError:
        raise SystemExit("Fichier déjà présent : aucune clé remplacée.") from None
    with os.fdopen(descriptor, "w") as destination:
        destination.write(f"SBC_API_KEY={secrets.token_urlsafe(32)}\n")
    print(f"Clé générée dans {args.file}. Ne pas versionner ni partager ce fichier publiquement.")


if __name__ == "__main__":
    main()
