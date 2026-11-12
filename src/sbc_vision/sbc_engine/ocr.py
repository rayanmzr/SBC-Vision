"""Lecture locale d'une capture et attribution des mots aux régions détectées."""

import json
import re
import unicodedata
from collections import defaultdict
from decimal import Decimal
from pathlib import Path

import pytesseract
from PIL import Image, ImageDraw, ImageFont, ImageOps

from .models import CardReading, Challenge, Condition, OcrInput
from .players import BASE_STATS, find_candidates, normalize_name

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


def ocr_words(image, *, lang, scale, psm=11, x=0, y=0):
    data = pytesseract.image_to_data(
        image, lang=lang, config=f"--psm {psm}", output_type=pytesseract.Output.DICT, timeout=20
    )
    return [
        {
            "text": text.strip(),
            "confidence": max(0, float(data["conf"][i])) / 100,
            "x": x + data["left"][i] / scale,
            "y": y + data["top"][i] / scale,
            "width": data["width"][i] / scale,
            "height": data["height"][i] / scale,
            "line": (data["block_num"][i], data["par_num"][i], data["line_num"][i]),
        }
        for i, text in enumerate(data["text"])
        if text.strip()
    ]


def read_regions(path, spec: OcrInput, *, lang="eng") -> list[dict]:
    with Image.open(path) as image:
        for region in spec.regions:
            box = region.bbox
            if box.x + box.width > image.width or box.y + box.height > image.height:
                raise ValueError(f"Région hors de l'image : {region.element_id}/{region.field}.")
        # Premier passage global ; les petits champs incertains sont ensuite relus isolément.
        prepared = ImageOps.autocontrast(ImageOps.grayscale(image)).resize(
            (image.width * 2, image.height * 2), Image.Resampling.LANCZOS
        )
        words = ocr_words(prepared, lang=lang, scale=2)
    results = []
    for region in spec.regions:
        box, lines, selected = region.bbox, defaultdict(list), []
        for word in words:
            x, y = word["x"] + word["width"] / 2, word["y"] + word["height"] / 2
            if box.x <= x < box.x + box.width and box.y <= y < box.y + box.height:
                selected.append(word)
                lines[word["line"]].append(word["text"])
        method = "global"
        if (
            region.field in {"name", "rating", "position", "stats", "item_score", "requirements"}
            and min((w["confidence"] for w in selected), default=0) < 0.75
        ):
            crop = prepared.crop(
                (box.x * 2, box.y * 2, (box.x + box.width) * 2, (box.y + box.height) * 2)
            ).resize((box.width * 3, box.height * 3), Image.Resampling.LANCZOS)
            retry = ocr_words(
                crop,
                lang=lang,
                scale=3,
                psm=6 if region.field in {"requirements", "stats"} else 7,
                x=box.x,
                y=box.y,
            )
            # Une seconde lecture ne devient jamais fiable simplement parce qu'elle est différente.
            if min((w["confidence"] for w in retry), default=0) > min(
                (w["confidence"] for w in selected), default=0
            ):
                selected, lines, method = retry, defaultdict(list), "region"
                for word in retry:
                    lines[word["line"]].append(word["text"])
        results.append(
            {
                "element_id": region.element_id,
                "field": region.field,
                "text": "\n".join(" ".join(line) for line in lines.values()),
                "confidence": min((w["confidence"] for w in selected), default=0),
                "bbox": box.model_dump(),
                "words": selected,
                "method": method,
            }
        )
    return results


def analyze(path, spec: OcrInput, db, *, lang="eng", minimum=0.75, regions=None) -> dict:
    if not 0 <= minimum <= 1:
        raise ValueError("Le seuil de confiance doit être compris entre 0 et 1.")
    # Un passage OCR existant peut être réutilisé, sans relire l'image.
    regions = read_regions(path, spec, lang=lang) if regions is None else regions
    grouped = defaultdict(dict)
    for region in regions:
        if region["field"] in {"name", "rating", "position", "stats", "item_score"}:
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
                stats = fields.get("stats")
                if stats:
                    # Les six intitulés et leurs valeurs doivent être lisibles, dans cet ordre.
                    tokens = stats["text"].upper().split()
                    labels, numbers = tokens[:6], tokens[6:]
                    if (
                        stats["confidence"] < minimum
                        or len(numbers) != 6
                        or labels not in [list(BASE_STATS)[:6], list(BASE_STATS)[6:]]
                        or any(not re.fullmatch(r"\d{1,2}", n) for n in numbers)
                    ):
                        issues.append("Statistiques à relire.")
                    else:
                        values["stats"] = dict(zip(labels, map(int, numbers), strict=True))
                        values["confidence"] = min(values["confidence"], stats["confidence"])
                score = fields.get("item_score")
                if score and score["confidence"] >= minimum:
                    try:
                        value = number(
                            re.sub(r"^\s*(?:item\s+)?score\s*:\s*", "", score["text"], flags=re.I)
                        )
                        if value <= 0:
                            raise ValueError("Score non positif.")
                        values["item_score"] = value
                        values["confidence"] = min(values["confidence"], score["confidence"])
                    except ValueError:
                        issues.append("Item Score à relire.")
                reading = CardReading.model_validate(values)
        candidates = find_candidates(db, reading) if reading and not issues else []
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
        "leagues": ["leagues", "leagues in squad", "ligues", "championnats"],
        "clubs": ["clubs"],
        "same_nation": [
            "players from the same nation",
            "players from the same countries regions",
            "joueurs du meme pays",
        ],
        "same_league": ["players from the same league", "joueurs de la meme ligue"],
        "same_club": ["players from the same club", "joueurs du meme club"],
        "team_rating": ["squad rating", "team rating", "note d equipe"],
        "chemistry": ["total chemistry", "chemistry", "collectif", "collectif total"],
        "item_score": ["item score", "score element", "score d element", "remaining item score"],
    }
    names = {normalize_name(label): key for key, values in labels.items() for label in values}
    rules, issues, progress, card_level, card_level_op = [], [], 0, None, "exact"
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
            joined[-1] += (" " if ":" in joined[-1] else ": ") + line
        else:
            joined.append(line)
    for line in joined:
        if normalize_name(line) in {"requirements", "conditions", "exigences"}:
            continue
        try:
            source_text = line
            # « Silver: Min. 5 Players » compte les argent, sans imposer cette qualité à tous.
            count = re.fullmatch(
                r"(gold|silver|bronze|or|argent)\s*:\s*(.+?)\s+(?:players|joueurs)", line, re.I
            )
            if count:
                level = {"or": "gold", "argent": "silver"}.get(count[1].lower(), count[1].lower())
                line = f"{level} players: {count[2]}"
            quality = re.fullmatch(
                r"(?:player quality|qualit[eé] des joueurs)\s*:\s*"
                r"(?:(min(?:imum)?|max(?:imum)?|exact(?:ly|ement)?)\.?\s+)?"
                r"(gold|silver|bronze|or|argent)",
                line,
                re.I,
            )
            if quality:
                level = {"or": "GOLD", "argent": "SILVER"}.get(
                    quality[2].lower(), quality[2].upper()
                )
                quality_op = (
                    "min"
                    if (quality[1] or "").lower().startswith("min")
                    else ("max" if (quality[1] or "").lower().startswith("max") else "exact")
                )
                if card_level is not None and (card_level, card_level_op) != (level, quality_op):
                    raise ValueError("Qualités de cartes contradictoires.")
                card_level, card_level_op = level, quality_op
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
                Condition(
                    metric=metric, op=op, value=number(amount), target=target, text=source_text
                )
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
                card_level_op=card_level_op,
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
    positions = list(report.get("positions", []))
    if not positions:
        for region in regions:
            if region["field"] == "slots":
                positions.extend(POSITIONS.get(p, p) for p in region["text"].upper().split())
    # Une seule condition peut s'étaler sur plusieurs lignes visuelles.
    text = "\n".join(
        " ".join(r["text"].splitlines()) if r["text"].count(":") == 1 else r["text"]
        for r in regions
        if r["field"] == "requirements"
    )
    return parse_requirements(text, db, positions=positions, market=market, budget=budget)


def edit_distance(expected, actual):
    # Chaque case compte le minimum d'insertions, suppressions ou substitutions.
    previous = list(range(len(actual) + 1))
    for i, left in enumerate(expected, 1):
        current = [i]
        for j, right in enumerate(actual, 1):
            current.append(
                min(previous[j] + 1, current[j - 1] + 1, previous[j - 1] + (left != right))
            )
        previous = current
    return previous[-1]


def evaluate(reports, references, *, minimum=0.75):
    if not 0 <= minimum <= 1:
        raise ValueError("Le seuil de confiance doit être compris entre 0 et 1.")

    def index(data):
        indexed = {}
        for capture in data if isinstance(data, list) else [data]:
            for region in capture["regions"]:
                key = capture["capture_id"], region["element_id"], region["field"]
                if not all(isinstance(v, str) and v.strip() for v in key) or key in indexed:
                    raise ValueError("Identifiants absents ou région annotée plusieurs fois.")
                if not isinstance(region["text"], str):
                    raise ValueError("Le texte d'une région doit être une chaîne.")
                indexed[key] = region
        return indexed

    def clean(text):
        # Les espaces sont harmonisés ; la casse, les accents et la ponctuation restent évalués.
        return " ".join(unicodedata.normalize("NFC", text).split())

    def summarize(rows):
        characters = sum(len(row["expected"]) for row in rows)
        errors = sum(row["edits"] for row in rows)
        return {
            "fields": len(rows),
            "characters": characters,
            "edits": errors,
            "cer": errors / characters,
            "exact_accuracy": sum(row["exact"] for row in rows) / len(rows),
            "unknown_rate": sum(row["unknown"] for row in rows) / len(rows),
        }

    observed, expected = index(reports), index(references)
    if not expected:
        raise ValueError("Il faut au moins une région annotée pour mesurer l'OCR.")
    details, groups = [], defaultdict(list)
    for key, reference in expected.items():
        truth = clean(reference["text"])
        if not truth:
            raise ValueError("Les régions de référence doivent contenir un texte non vide.")
        prediction = observed.get(key, {"text": "", "confidence": 0})
        text, confidence = clean(prediction["text"]), prediction["confidence"]
        if type(confidence) not in (int, float) or not 0 <= confidence <= 1:
            raise ValueError("Confiance OCR invalide.")
        known = bool(text) and confidence >= minimum
        row = {
            "capture_id": key[0],
            "element_id": key[1],
            "field": key[2],
            "expected": truth,
            "predicted": text,
            "edits": edit_distance(truth, text),
            "exact": known and text == truth,
            "unknown": not known,
        }
        details.append(row)
        groups[key[2]].append(row)
    return {
        "minimum_confidence": minimum,
        "summary": summarize(details),
        "by_field": {field: summarize(rows) for field, rows in groups.items()},
        "missing_regions": len(expected.keys() - observed.keys()),
        "unexpected_regions": len(observed.keys() - expected.keys()),
        "details": details,
    }


def evaluation_demo(folder, *, lang="eng", labels=None):
    """Créer et lire des champs fictifs, sans compte EA ni catalogue externe."""
    folder = Path(folder)
    folder.mkdir(parents=True, exist_ok=True)
    if labels is None:
        labels = [
            ("card-1", "name", "ALEX EXEMPLE"),
            ("card-1", "rating", "83"),
            ("card-1", "position", "CM"),
            ("card-2", "name", "MINA TEST"),
            ("card-2", "rating", "84"),
            ("card-2", "position", "ST"),
        ]
    image = Image.new("RGB", (800, len(labels) * 70 + 40), "white")
    draw, font = ImageDraw.Draw(image), ImageFont.load_default(size=36)
    regions, references = [], []
    for i, (element_id, field, text) in enumerate(labels):
        y = 20 + i * 70
        draw.text((30, y + 8), text, fill="black", font=font)
        region = {
            "element_id": element_id,
            "field": field,
            "bbox": {"x": 10, "y": y, "width": 750, "height": 60},
        }
        regions.append(region)
        references.append({**region, "text": text})
    path = folder / "ocr_demo.png"
    image.save(path)
    spec = OcrInput(capture_id="synthetic-ocr-demo", regions=regions)
    report = {
        "capture_id": spec.capture_id,
        "regions": read_regions(path, spec, lang=lang),
        "tesseract_version": str(pytesseract.get_tesseract_version()),
        "lang": lang,
    }
    expected = {"capture_id": spec.capture_id, "regions": references}
    for name, data in [("report", report), ("expected", expected)]:
        (folder / f"ocr_demo.{name}.json").write_text(
            json.dumps(data, ensure_ascii=False, indent=2) + "\n"
        )
    return report, expected
