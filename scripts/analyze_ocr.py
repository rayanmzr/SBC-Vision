"""Envoyer une capture et un OcrInput existant au lecteur HTTP de Rayan."""

import argparse
import json
import os
import sys
from pathlib import Path

import httpx
from PIL import Image

from sbc_vision.contracts.ocr import OcrAnalysisRequest, OcrAnalysisResponse
from sbc_vision.sbc_engine.models import OcrInput


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("image", type=Path)
    parser.add_argument("--regions", type=Path, required=True, help="JSON au format OcrInput")
    parser.add_argument("--url", default="http://127.0.0.1:8000")
    parser.add_argument("--minimum", type=float, default=0.75)
    parser.add_argument("--market", choices=["pc", "ps"], default="pc")
    parser.add_argument("--budget", type=int, default=0)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    media = {".png": "image/png", ".jpg": "image/jpeg", ".jpeg": "image/jpeg"}.get(
        args.image.suffix.lower()
    )
    if media is None:
        parser.error("Choisir une image PNG ou JPEG.")
    try:
        spec = OcrInput.model_validate_json(args.regions.read_text())
        with Image.open(args.image) as image:
            width, height = image.size
        metadata = OcrAnalysisRequest(
            image={"width": width, "height": height},
            specification=spec,
            minimum_confidence=args.minimum,
            market=args.market,
            budget=args.budget,
        )
        key = os.getenv("SBC_API_KEY", "")
        if not key and os.getenv("SBC_API_KEY_FILE"):
            key = Path(os.environ["SBC_API_KEY_FILE"]).read_text().strip()
        with args.image.open("rb") as source:
            response = httpx.post(
                args.url.rstrip("/") + "/api/v1/ocr/analyze",
                files={"image": (args.image.name, source, media)},
                data={"metadata": metadata.model_dump_json()},
                headers={"Authorization": f"Bearer {key}"} if key else {},
                timeout=35,
            )
        if response.status_code != 200:
            print(f"OCR refusé : HTTP {response.status_code}.", file=sys.stderr)
            return 1
        report = OcrAnalysisResponse.model_validate_json(response.content)
        text = json.dumps(report.model_dump(mode="json"), ensure_ascii=False, indent=2) + "\n"
        if args.output:
            args.output.parent.mkdir(parents=True, exist_ok=True)
            args.output.write_text(text)
        else:
            print(text, end="")
    except (OSError, ValueError, httpx.HTTPError) as exc:
        print(f"Analyse OCR impossible ({type(exc).__name__}).", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
