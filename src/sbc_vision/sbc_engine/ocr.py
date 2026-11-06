"""Lecture locale d'une capture et attribution des mots aux régions détectées."""

import json
import re
from collections import defaultdict
from decimal import Decimal

import pytesseract
from PIL import Image, ImageOps

from .models import CardReading, Challenge, Condition, OcrInput
from .players import find_candidates, normalize_name

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
        if region["field"] in {"name", "rating", "position", "item_score"}:
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
                # Saber peut compléter la lecture par les attributs visuels des logos/cartes.
                values.update(spec.attributes.get(element_id, {}))
                position = fields.get("position")
                if position and position["confidence"] >= minimum:
                    value = position["text"].strip().upper()
                    values["position"] = POSITIONS.get(value, value)
                score = fields.get("item_score")
                if score and score["confidence"] >= minimum:
                    try:
                        value = number(score["text"])
                        if value <= 0:
                            raise ValueError("Score non positif.")
                        values["item_score"] = value
                        values["confidence"] = min(values["confidence"], score["confidence"])
                    except ValueError:
                        issues.append("Item Score à relire.")
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
    return {
        "capture_id": spec.capture_id,
        "regions": regions,
        "cards": cards,
        "positions": spec.positions,
    }


def number(text):
    value = text.strip().replace(" ", "").replace("\u00a0", "")
    if re.fullmatch(r"\d+(?:[.,]\d+)?[kKmM]", value):
        amount = Decimal(value[:-1].replace(",", ".")) * (
            1000 if value[-1].lower() == "k" else 1000000
        )
        if amount != amount.to_integral_value():
            raise ValueError("Le score doit être entier.")
        return int(amount)
    if not re.fullmatch(r"\d+(?:[,.]\d{3})*", value):
        raise ValueError(f"Nombre incertain : {text}")
    return int(value.replace(",", "").replace(".", ""))


def resolve_target(db, label, field):
    if re.fullmatch(r"(?:id\s*)?#?\d+", label):
        return int(re.sub(r"\D", "", label))
    if not normalize_name(label):
        raise ValueError("Nom de pays, ligue ou club illisible.")
    matches = {
        card[f"{field}_id"]
        for row in db.execute("SELECT data FROM cards")
        if normalize_name((card := json.loads(row["data"])).get(f"{field}_name") or "")
        == normalize_name(label)
    }
    if len(matches) != 1:
        raise ValueError(f"{field} « {label} » absent ou ambigu dans le catalogue.")
    return matches.pop()


def parse_requirements(text, db, *, positions, market, budget):
    # On reconnaît des types de conditions, jamais le nom d'un SBC particulier.
    labels = {
        "players": ["number of players", "number of players in the squad", "nombre de joueurs"],
        "rating": ["player rating", "minimum ovr", "note individuelle", "note des joueurs"],
        "rare": ["rare players", "joueurs rares", "cartes rares"],
        "nations": ["nationalities", "nationalites", "countries regions"],
        "leagues": ["leagues", "ligues", "championnats"],
        "clubs": ["clubs"],
        "same_nation": ["players from the same nation", "joueurs du meme pays"],
        "same_league": ["players from the same league", "joueurs de la meme ligue"],
        "same_club": ["players from the same club", "joueurs du meme club"],
        "team_rating": ["squad rating", "team rating", "note d equipe"],
        "chemistry": ["total chemistry", "chemistry", "collectif", "collectif total"],
        "item_score": ["item score", "score element", "score d element", "remaining item score"],
    }
    names = {normalize_name(label): key for key, values in labels.items() for label in values}
    rules, issues, progress, card_level = [], [], 0, None
    positions = [POSITIONS.get(p.strip().upper(), p.strip().upper()) for p in positions]
    if any(p not in set(POSITIONS.values()) | {"CF", "LWB", "RWB", "LF", "RF"} for p in positions):
        issues.append("Un poste doit être relu.")
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    # Tesseract peut séparer un libellé et sa valeur sur deux lignes.
    joined = []
    for line in lines:
        if joined and re.fullmatch(
            r"(?:(?:min|max|exact|minimum|maximum)\.?\s*)?[\d ,.]+", line, re.I
        ):
            joined[-1] += ": " + line
        else:
            joined.append(line)
    for line in joined:
        if normalize_name(line) in {"requirements", "conditions", "exigences"}:
            continue
        try:
            quality = re.fullmatch(
                r"(?:player quality|qualit[eé] des joueurs)\s*:\s*"
                r"(?:exact(?:ly|ement)?\s+)?(gold|silver|bronze|or|argent)",
                line,
                re.I,
            )
            if quality:
                level = {"or": "GOLD", "argent": "SILVER"}.get(
                    quality[1].lower(), quality[1].upper()
                )
                if card_level is not None and card_level != level:
                    raise ValueError("Qualités de cartes contradictoires.")
                card_level = level
                continue
            match = re.fullmatch(
                r"(.+?)(?:\s*:\s*|\s+(?=(?:min|max|exact)))"
                r"(?:(min(?:imum)?|max(?:imum)?|exact(?:ly|ement)?)\.?\s*)?"
                r"([\d .,]+(?:[kKmM])?(?:\s*/\s*[\d .,]+)?)",
                line,
                re.I,
            )
            if not match:
                raise ValueError(f"Condition non reconnue : {line}")
            label, operator, amount = match.groups()
            op = (
                "max"
                if (operator or "").lower().startswith("max")
                else ("min" if (operator or "").lower().startswith("min") else "exact")
            )
            metric = names.get(normalize_name(label))
            target = None
            if "/" in amount:
                before, amount = amount.split("/")
                if metric == "item_score":
                    progress = number(before)
            if metric == "item_score":
                op = "min" if operator is None else op
            if metric is None:
                target_match = re.fullmatch(r"(nation|pays|league|ligue|club)\s+(.+)", label, re.I)
                rated = re.fullmatch(
                    r"(?:players rated|joueurs de note)\s+(\d+)\s*(?:or higher|minimum|\+)?",
                    label,
                    re.I,
                )
                quality = normalize_name(label)
                if rated:
                    metric, target = "rated", int(rated[1])
                elif target_match:
                    kind, value = target_match.groups()
                    metric = {"pays": "nation", "ligue": "league"}.get(kind.lower(), kind.lower())
                    target = resolve_target(db, value, metric)
                elif quality in {
                    "goldplayers",
                    "joueursor",
                    "silverplayers",
                    "joueursargent",
                    "bronzeplayers",
                    "joueursbronze",
                }:
                    metric = "quality"
                    target = (
                        "GOLD"
                        if quality in {"goldplayers", "joueursor"}
                        else (
                            "SILVER" if quality in {"silverplayers", "joueursargent"} else "BRONZE"
                        )
                    )
                else:
                    raise ValueError(f"Condition non prise en charge : {line}")
            if operator is None and metric not in {"players", "item_score"}:
                raise ValueError(f"Minimum, maximum ou valeur exacte à confirmer : {line}")
            rules.append(
                Condition(metric=metric, op=op, value=number(amount), target=target, text=line)
            )
        except ValueError as error:
            issues.append(str(error))
    if not rules and card_level is None:
        issues.append("Aucune condition exploitable n'a été lue.")
    challenge = None
    if not issues:
        try:
            challenge = Challenge(
                rules_version="dynamic-v1",
                mode="score" if any(r.metric == "item_score" for r in rules) else "squad",
                positions=positions,
                market=market,
                budget=budget,
                conditions=rules,
                score_progress=progress,
                card_level=card_level,
            )
        except ValueError as error:
            issues.append(str(error))
    return {
        "ready": not issues,
        "challenge": challenge.model_dump() if challenge else None,
        "issues": issues,
        "raw_text": text,
    }


def challenge_from_ocr(report, db, *, market, budget, minimum=0.75):
    regions = [r for r in report["regions"] if r["field"] in {"requirements", "slots"}]
    if not regions or any(r["confidence"] < minimum for r in regions):
        return {
            "ready": False,
            "challenge": None,
            "issues": ["Conditions absentes ou lecture incertaine."],
        }
    positions = report.get("positions", [])
    if not positions:
        for region in regions:
            if region["field"] == "slots":
                positions.extend(POSITIONS.get(p, p) for p in region["text"].upper().split())
    text = "\n".join(r["text"] for r in regions if r["field"] == "requirements")
    return parse_requirements(text, db, positions=positions, market=market, budget=budget)
