"""Lecture locale d'une capture et attribution des mots aux régions détectées."""

import re
from collections import defaultdict

import pytesseract
from PIL import Image, ImageOps

from .inventory import find_candidates
from .models import CardReading, OcrInput

POSITIONS = {
    "G": "GK",
    "DG": "LB",
    "DD": "RB",
    "DC": "CB",
    "MDC": "CDM",
    "MC": "CM",
    "MOC": "CAM",
    "MG": "LM",
    "MD": "RM",
    "AG": "LW",
    "AD": "RW",
    "BU": "ST",
}


def read_regions(path, spec: OcrInput, *, lang="eng") -> list[dict]:
    with Image.open(path) as image:
        for region in spec.regions:
            box = region.bbox
            if box.x + box.width > image.width or box.y + box.height > image.height:
                raise ValueError(f"Région hors de l'image : {region.element_id}/{region.field}.")
        # Un seul passage OCR par capture ; agrandir aide à lire les petits caractères.
        prepared = ImageOps.autocontrast(ImageOps.grayscale(image)).resize(
            (image.width * 2, image.height * 2), Image.Resampling.LANCZOS
        )
        data = pytesseract.image_to_data(
            prepared, lang=lang, config="--psm 11", output_type=pytesseract.Output.DICT, timeout=20
        )
    words = []
    for i, text in enumerate(data["text"]):
        if text.strip():
            words.append(
                {
                    "text": text.strip(),
                    "confidence": max(0, float(data["conf"][i])) / 100,
                    "x": data["left"][i] / 2,
                    "y": data["top"][i] / 2,
                    "width": data["width"][i] / 2,
                    "height": data["height"][i] / 2,
                    "line": (data["block_num"][i], data["par_num"][i], data["line_num"][i]),
                }
            )
    results = []
    for region in spec.regions:
        box, lines, selected = region.bbox, defaultdict(list), []
        for word in words:
            x, y = word["x"] + word["width"] / 2, word["y"] + word["height"] / 2
            if box.x <= x < box.x + box.width and box.y <= y < box.y + box.height:
                selected.append(word)
                lines[word["line"]].append(word["text"])
        results.append(
            {
                "element_id": region.element_id,
                "field": region.field,
                "text": "\n".join(" ".join(line) for line in lines.values()),
                "confidence": min((w["confidence"] for w in selected), default=0),
                "bbox": box.model_dump(),
                "words": selected,
            }
        )
    return results


def analyze(path, spec: OcrInput, db, *, lang="eng", minimum=0.75) -> dict:
    if not 0 <= minimum <= 1:
        raise ValueError("Le seuil de confiance doit être compris entre 0 et 1.")
    regions = read_regions(path, spec, lang=lang)
    grouped = defaultdict(dict)
    for region in regions:
        if region["field"] in {"name", "rating", "position"}:
            grouped[region["element_id"]][region["field"]] = region
    cards = []
    for element_id, fields in grouped.items():
        issues = [
            f"Champ absent ou incertain : {key}"
            for key in ("name", "rating")
            if key not in fields or fields[key]["confidence"] < minimum
        ]
        reading = None
        if not issues:
            name, rating = fields["name"]["text"].strip(), fields["rating"]["text"].strip()
            if not any(c.isalpha() for c in name) or not re.fullmatch(r"[1-9]\d?", rating):
                issues.append("Le nom ou la note doit être relu.")
            else:
                values = {
                    "capture_id": spec.capture_id,
                    "element_id": element_id,
                    "name": name,
                    "rating": int(rating),
                    "confidence": min(fields[k]["confidence"] for k in ("name", "rating")),
                }
                position = fields.get("position")
                if position and position["confidence"] >= minimum:
                    value = position["text"].strip().upper()
                    values["position"] = POSITIONS.get(value, value)
                reading = CardReading.model_validate(values)
        candidates = find_candidates(db, reading) if reading else []
        cards.append(
            {
                "element_id": element_id,
                "reading": reading.model_dump() if reading else None,
                "candidate_ids": [c["id"] for c in candidates],
                "issues": issues,
                "needs_confirmation": True,
            }
        )
    # Les textes bruts et les confiances restent disponibles pour corriger une lecture.
    return {"capture_id": spec.capture_id, "regions": regions, "cards": cards}
