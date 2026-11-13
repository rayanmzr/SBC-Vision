"""Client manuel de l'API de perception ; envoie uniquement le fichier choisi."""

import argparse
import json
import sys
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from sbc_vision.contracts.perception import PerceptionResponse


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("image", type=Path)
    parser.add_argument("--url", default="http://127.0.0.1:8000")
    parser.add_argument("--capture-id", default="manual-capture")
    args = parser.parse_args()
    media = {".png": "image/png", ".jpg": "image/jpeg", ".jpeg": "image/jpeg"}.get(
        args.image.suffix.lower()
    )
    if media is None:
        parser.error("Choisir une image .png, .jpg ou .jpeg.")
    query = urlencode({"capture_id": args.capture_id})
    try:
        request = Request(
            f"{args.url.rstrip('/')}/api/v1/perception/analyze?{query}",
            data=args.image.read_bytes(),
            headers={"Content-Type": media},
            method="POST",
        )
        with urlopen(request, timeout=30) as response:
            result = PerceptionResponse.model_validate_json(response.read())
    except HTTPError as exc:
        print(f"HTTP {exc.code}: {exc.read().decode('utf-8', errors='replace')}", file=sys.stderr)
        return 1
    except (OSError, URLError, ValueError) as exc:
        print(f"Analyse impossible : {exc}", file=sys.stderr)
        return 1
    print(json.dumps(result.model_dump(mode="json"), ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
