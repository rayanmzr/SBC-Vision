"""Construit un split WebUI au format commun (COCO + manifeste).

    python -m sbc_vision.perception.datasets.build_webui \
        --pages <extrait>/train_split_web7k \
        --data-root <extrait> \
        --split train --out data/processed/webui
"""

import argparse
import collections
import json
from concurrent.futures import ProcessPoolExecutor
from dataclasses import dataclass
from pathlib import Path

import numpy as np
from PIL import Image

from sbc_vision.perception.datasets.quality import PageQuality, assess_page
from sbc_vision.perception.datasets.records import (
    BoxRecord,
    ImageRecord,
    file_sha256,
    write_corpus,
)
from sbc_vision.perception.datasets.webui import LabeledElement, WebUIPage, iter_pages


@dataclass(frozen=True)
class _Labeled:
    """Une capture étiquetée et contrôlée."""

    page: WebUIPage
    domain: str
    size: tuple[int, int]
    scale: float
    sha256: str
    labels: tuple[LabeledElement, ...]
    quality: PageQuality


@dataclass(frozen=True)
class _Rejected:
    """Une capture illisible ou incohérente, et pourquoi."""

    page: WebUIPage
    error: str


def _process(sample_dir: Path) -> list[_Labeled | _Rejected]:
    results = []
    for page in iter_pages(sample_dir):
        try:
            with Image.open(page.screenshot) as image:
                size = image.size
                gray = np.asarray(image.convert("L"), dtype=np.float32)
            scale, labels = page.labels(size)
            domain = page.domain
        except (OSError, ValueError, KeyError) as exc:
            results.append(_Rejected(page, f"{type(exc).__name__}: {exc}"))
            continue
        quality = assess_page(gray, [element.box for element in labels])
        kept = tuple(e for e, flat in zip(labels, quality.uniform, strict=True) if not flat)
        sha = file_sha256(page.screenshot)
        results.append(_Labeled(page, domain, size, scale, sha, kept, quality))
    return results


def build_split(pages_dir: Path, data_root: Path, split: str, out: Path, workers: int) -> dict:
    sample_dirs = sorted(path for path in pages_dir.iterdir() if path.is_dir())
    images: list[ImageRecord] = []
    boxes: list[BoxRecord] = []
    errors: list[str] = []
    per_class: collections.Counter = collections.Counter()
    empty = uniform_boxes = 0
    excluded: list[str] = []
    with ProcessPoolExecutor(max_workers=workers) as pool:
        for batch in pool.map(_process, sample_dirs, chunksize=16):
            for item in batch:
                page = item.page
                if isinstance(item, _Rejected):
                    errors.append(f"{page.sample_id}/{page.device}: {item.error}")
                    continue
                uniform_boxes += item.quality.uniform_count
                if item.quality.excluded:
                    excluded.append(f"{page.sample_id}/{page.device}")
                    continue
                image_id = len(images) + 1
                images.append(
                    ImageRecord(
                        image_id=image_id,
                        file_name=str(page.screenshot.relative_to(data_root)),
                        width=item.size[0],
                        height=item.size[1],
                        source="webui",
                        split=split,
                        domain=item.domain,
                        group=page.sample_id,
                        device=page.device,
                        sha256=item.sha256,
                        extra={"url": page.url, "scale": round(item.scale, 4)},
                    )
                )
                empty += not item.labels
                for element in item.labels:
                    per_class[element.kind.value] += 1
                    boxes.append(
                        BoxRecord(
                            image_id=image_id,
                            kind=element.kind,
                            box=element.box,
                            extra={"role": element.role, "name": element.name},
                        )
                    )
    write_corpus(out, split, images, boxes)
    stats = {
        "split": split,
        "pages": len({image.group for image in images}),
        "images": len(images),
        "domains": len({image.domain for image in images}),
        "boxes": len(boxes),
        "images_without_boxes": empty,
        "uniform_boxes_dropped": uniform_boxes,
        "images_excluded_uniform": len(excluded),
        "excluded_examples": excluded[:20],
        "per_class": dict(per_class.most_common()),
        "errors": len(errors),
        "error_examples": errors[:10],
    }
    (out / f"{split}.stats.json").write_text(json.dumps(stats, indent=2), encoding="utf-8")
    return stats


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--pages", type=Path, required=True)
    parser.add_argument("--data-root", type=Path, required=True)
    parser.add_argument("--split", required=True)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--workers", type=int, default=4)
    args = parser.parse_args()
    stats = build_split(args.pages, args.data_root, args.split, args.out, args.workers)
    print(json.dumps(stats, indent=2))


if __name__ == "__main__":
    main()
