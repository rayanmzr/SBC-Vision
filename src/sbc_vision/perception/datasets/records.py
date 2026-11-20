"""Format commun des corpus : manifeste JSONL et annotations COCO.

Le manifeste décrit chaque capture (provenance, domaine, groupe de split, empreinte, échelle) ;
les annotations COCO portent les boîtes. Les identifiants de catégorie COCO valent l'indice de
la classe dans `DETECTOR_CLASSES` plus un. `write_corpus` et `read_corpus` sont les deux seules
portes d'entrée et de sortie d'un corpus.
"""

import hashlib
import json
from dataclasses import asdict, dataclass, field
from pathlib import Path

from sbc_vision.contracts.perception import ElementKind
from sbc_vision.perception.ontology import DETECTOR_CLASSES, class_id


@dataclass(frozen=True)
class ImageRecord:
    image_id: int
    file_name: str  # relatif à la racine des données
    width: int
    height: int
    source: str  # `webui` (corpus WebUI) ou `capture` (sites capturés par nous)
    split: str
    domain: str
    group: str  # unité indivisible entre splits : page WebUI, page capturée…
    device: str
    sha256: str  # empreinte de la capture, pour versionner les données
    scale: float  # pixels de capture par pixel CSS
    extra: dict = field(default_factory=dict)


@dataclass(frozen=True)
class BoxRecord:
    image_id: int
    kind: ElementKind
    box: tuple[float, float, float, float]  # x1, y1, x2, y2
    extra: dict = field(default_factory=dict)


def coco_category_id(kind: ElementKind) -> int:
    return class_id(kind) + 1


def kind_from_category_id(category_id: int) -> ElementKind:
    if not 1 <= category_id <= len(DETECTOR_CLASSES):
        raise ValueError(f"catégorie COCO inconnue : {category_id}")
    return DETECTOR_CLASSES[category_id - 1]


def file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def coco_document(images: list[ImageRecord], boxes: list[BoxRecord]) -> dict:
    annotations = []
    for index, record in enumerate(boxes, start=1):
        x1, y1, x2, y2 = record.box
        annotations.append(
            {
                "id": index,
                "image_id": record.image_id,
                "category_id": coco_category_id(record.kind),
                "bbox": [round(x1, 2), round(y1, 2), round(x2 - x1, 2), round(y2 - y1, 2)],
                "area": round((x2 - x1) * (y2 - y1), 2),
                "iscrowd": 0,
                **({"extra": record.extra} if record.extra else {}),
            }
        )
    return {
        "images": [
            {
                "id": image.image_id,
                "file_name": image.file_name,
                "width": image.width,
                "height": image.height,
            }
            for image in images
        ],
        "annotations": annotations,
        "categories": [
            {"id": coco_category_id(kind), "name": kind.value} for kind in DETECTOR_CLASSES
        ],
    }


def write_corpus(
    directory: Path, split: str, images: list[ImageRecord], boxes: list[BoxRecord]
) -> None:
    directory.mkdir(parents=True, exist_ok=True)
    (directory / f"{split}.coco.json").write_text(
        json.dumps(coco_document(images, boxes), ensure_ascii=False), encoding="utf-8"
    )
    with (directory / f"{split}.manifest.jsonl").open("w", encoding="utf-8") as handle:
        for image in images:
            handle.write(json.dumps(asdict(image), ensure_ascii=False) + "\n")


def read_manifest(path: Path) -> list[ImageRecord]:
    with path.open(encoding="utf-8") as handle:
        return [ImageRecord(**json.loads(line)) for line in handle if line.strip()]


@dataclass(frozen=True)
class Corpus:
    images: list[ImageRecord]  # dans l'ordre du manifeste
    boxes: dict[int, list[BoxRecord]]  # par image, dans l'ordre d'écriture


def read_corpus(directory: Path, split: str) -> Corpus:
    """Inverse de `write_corpus`."""
    images = read_manifest(directory / f"{split}.manifest.jsonl")
    document = json.loads((directory / f"{split}.coco.json").read_text(encoding="utf-8"))
    if [image["id"] for image in document["images"]] != [image.image_id for image in images]:
        raise ValueError(f"{split} : annotations COCO et manifeste désaccordés")
    boxes: dict[int, list[BoxRecord]] = {image.image_id: [] for image in images}
    for annotation in sorted(document["annotations"], key=lambda a: a["id"]):
        x, y, w, h = annotation["bbox"]
        boxes[annotation["image_id"]].append(
            BoxRecord(
                image_id=annotation["image_id"],
                kind=kind_from_category_id(annotation["category_id"]),
                box=(x, y, x + w, y + h),
                extra=annotation.get("extra", {}),  # écrit seulement s'il n'est pas vide
            )
        )
    return Corpus(images, boxes)
