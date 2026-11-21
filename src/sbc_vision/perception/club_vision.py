"""Observation du club à partir des pixels uniquement, sans navigateur ni HTML."""

import hashlib
from collections import defaultdict
from io import BytesIO

import cv2
import numpy as np
from PIL import ImageOps

from sbc_vision.contracts.ocr import OcrAnalysisRequest, VisionFrame
from sbc_vision.sbc_engine.ocr import ocr_words
from sbc_vision.sbc_engine.players import BASE_STATS, normalize_name


def box(x, y, width, height):
    return {
        "x": round(x),
        "y": round(y),
        "width": max(1, round(width)),
        "height": max(1, round(height)),
    }


def observe_club(capture, detector, reader, database):
    """Les lignes OCR ancrent les régions ; YOLO ou OpenCV corroborent les miniatures."""
    image = capture.image
    width, height = image.size
    scale = min(1, 1512 / width)
    words = ocr_words(
        ImageOps.grayscale(image).resize((round(width * scale), round(height * scale))),
        lang=reader.language,
        scale=scale,
    )
    lines = defaultdict(list)
    for word in words:
        lines[word["line"]].append(word)
    headings = [
        normalize_name(" ".join(w["text"] for w in line))
        for line in lines.values()
        if min(w["y"] for w in line) < height * 0.17 and min(w["x"] for w in line) > width * 0.06
    ]
    scene = (
        "players"
        if any("clubplayers" in h for h in headings)
        else "club"
        if "club" in headings
        else "other"
    )
    if scene == "club":
        # Le titre « Players » est blanc sur une photo : isoler les pixels clairs
        # permet une relecture locale sans recourir au texte du navigateur.
        x, y = round(width * 0.20), round(height * 0.15)
        crop = ImageOps.grayscale(image).crop((x, y, round(width * 0.50), round(height * 0.28)))
        words += ocr_words(
            crop.point(lambda p: 0 if p > 230 else 255),
            lang=reader.language,
            scale=1,
            x=x,
            y=y,
        )
    controls = {}
    for word in words:
        label = normalize_name(word["text"])
        if word["confidence"] < 0.8:
            continue
        key = label if label in {"club", "players", "previous", "next"} else None
        if key in {"previous", "next"} and not (
            word["y"] > height * 0.75 and word["x"] < width * 0.7
        ):
            continue
        if key == "club" and word["x"] > width * 0.12:
            continue
        if key == "players" and (scene != "club" or word["x"] < width * 0.12):
            continue
        if key:
            controls[key] = box(word["x"], word["y"], word["width"], word["height"])
    area = (
        box(width * 0.14, height * 0.24, width * 0.55, height * 0.64)
        if scene == "players"
        else None
    )
    # Le hachage de la liste ignore l'horloge et les autres zones de l'écran.
    crop = (
        image.crop((area["x"], area["y"], area["x"] + area["width"], area["y"] + area["height"]))
        if area
        else image
    )
    fingerprint = hashlib.sha256(np.asarray(crop.resize((64, 96)).convert("L")) // 16).hexdigest()
    rows, regions = [], []
    if area:
        predictions = detector.detect(np.asarray(image))
        stats = [
            w
            for w in words
            if w["text"].upper() in BASE_STATS
            and width * 0.18 < w["x"] < width * 0.68
            and height * 0.24 < w["y"] < height * 0.87
        ]
        groups = []
        for word in sorted(stats, key=lambda w: w["y"]):
            group = next((g for g in groups if abs(g[0]["y"] - word["y"]) < height * 0.008), None)
            if group is None:
                groups.append([word])
            else:
                group.append(word)
        for group in groups:
            group.sort(key=lambda w: w["x"])
            labels = [w["text"].upper() for w in group]
            if labels not in [list(BASE_STATS)[:6], list(BASE_STATS)[6:]]:
                continue
            left, top = group[0]["x"], min(w["y"] for w in group)
            span = group[-1]["x"] + group[-1]["width"] - left
            cw, ch = span / 2.30, span / 2.30 / 0.70
            miniature = box(left - 1.16 * cw, top - 0.45 * ch, cw, ch)
            if miniature["y"] < area["y"] or miniature["y"] + ch > area["y"] + area["height"]:
                continue  # Une ligne coupée doit être relue après défilement.
            identifier = f"vision-row-{len(rows)}"
            edges = cv2.Canny(
                np.asarray(
                    image.crop(
                        (miniature["x"], miniature["y"], miniature["x"] + cw, miniature["y"] + ch)
                    ).convert("L")
                ),
                40,
                120,
            )
            if np.count_nonzero(edges) < edges.size * 0.01:
                continue
            matched = any(
                kind == "card"
                and score >= 0.61
                and abs(bounds[0] - miniature["x"]) < cw * 0.4
                and abs(bounds[1] - miniature["y"]) < ch * 0.4
                for kind, bounds, score in predictions
            )
            rows.append(
                {
                    "element_id": identifier,
                    "bbox": miniature,
                    "detector": "yolo" if matched else "opencv-ocr",
                }
            )
            fields = {
                "name": box(left, top - 0.45 * ch, cw * 3, ch * 0.28),
                "rating": box(
                    miniature["x"] + 0.03 * cw, miniature["y"] + 0.12 * ch, cw * 0.29, ch * 0.15
                ),
                "position": box(miniature["x"], miniature["y"] + 0.28 * ch, cw * 0.40, ch * 0.12),
                "stats": box(left - 2, top - 3, span + 6, ch * 0.32),
            }
            regions.extend(
                {"element_id": identifier, "field": field, "bbox": value}
                for field, value in fields.items()
            )
    ocr = None
    data = BytesIO()
    image.save(data, format="PNG")
    if regions:
        specification = OcrAnalysisRequest(
            image={"width": width, "height": height},
            specification={"capture_id": capture.capture_id, "regions": regions},
        )
        ocr = reader.analyze(data.getvalue(), specification, database, words=words)
        ocr.region_source, ocr.automatic_detection = "detected", True
    frame = VisionFrame(
        capture_id=capture.capture_id,
        image={"width": width, "height": height},
        model_name=f"{detector.name}+club-opencv-ocr",
        image_sha256=hashlib.sha256(data.getvalue()).hexdigest(),
        screen_hash=fingerprint,
        scene=scene,
        list_bbox=area,
        controls=controls,
        rows=rows,
        ocr=ocr,
    )
    if database:
        # Preuves privées locales : image exacte, régions et textes OCR, sans état du navigateur.
        directory = database.parent / "vision_proof"
        directory.mkdir(parents=True, exist_ok=True)
        key = hashlib.sha256(capture.capture_id.encode()).hexdigest()
        (directory / f"{key}.png").write_bytes(data.getvalue())
        (directory / f"{key}.json").write_text(frame.model_dump_json(indent=2))
    return frame
