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
from pathlib import Path

import numpy as np
from PIL import Image

from sbc_vision.perception.datasets.quality import DEFAULT_QUALITY_RULES, QualityRules, assess_page
from sbc_vision.perception.datasets.records import (
    BoxRecord,
    ImageRecord,
    file_sha256,
    write_corpus,
)
from sbc_vision.perception.datasets.webui import (
    DESKTOP_DEVICES,
    LabeledElement,
    WebUIPage,
    iter_pages,
)


def _process(sample_dir: Path, devices: tuple[str, ...], rules: QualityRules):
    results = []
    for webui_page in iter_pages(sample_dir, devices):
        try:
            with Image.open(webui_page.screenshot) as image:
                size = image.size
                gray = np.asarray(image.convert("L"), dtype=np.float32)
            scale, labels = webui_page.labels(size)
        except (OSError, ValueError, KeyError) as exc:
            error = f"{type(exc).__name__}: {exc}"
            results.append((webui_page, None, None, None, [], None, error))
            continue
        quality = assess_page(gray, [element.box for element in labels], rules)
        kept = [element for element, flat in zip(labels, quality.uniform, strict=True) if not flat]
        sha = file_sha256(webui_page.screenshot)
        results.append((webui_page, size, scale, sha, kept, quality, None))
    return results


def build_split(
    pages_dir: Path,
    data_root: Path,
    split: str,
    out: Path,
    devices: tuple[str, ...],
    workers: int,
    limit: int | None = None,
    rules: QualityRules = DEFAULT_QUALITY_RULES,
) -> dict:
    sample_dirs = sorted(path for path in pages_dir.iterdir() if path.is_dir())
    if limit:
        sample_dirs = sample_dirs[:limit]
    images: list[ImageRecord] = []
    boxes: list[BoxRecord] = []
    errors: list[str] = []
    per_class: collections.Counter = collections.Counter()
    empty = uniform_boxes = 0
    excluded: list[str] = []
    with ProcessPoolExecutor(max_workers=workers) as pool:
        jobs = len(sample_dirs)
        batches = pool.map(_process, sample_dirs, [devices] * jobs, [rules] * jobs, chunksize=16)
        for batch in batches:
            for page, size, scale, sha, labels, quality, error in batch:
                page: WebUIPage
                labels: list[LabeledElement]
                if error:
                    errors.append(f"{page.sample_id}/{page.device}: {error}")
                    continue
                uniform_boxes += quality.uniform_count
                if quality.excluded:
                    excluded.append(f"{page.sample_id}/{page.device}")
                    continue
                image_id = len(images) + 1
                images.append(
                    ImageRecord(
                        image_id=image_id,
                        file_name=str(page.screenshot.relative_to(data_root)),
                        width=size[0],
                        height=size[1],
                        source="webui",
                        split=split,
                        domain=page.domain,
                        group=page.sample_id,
                        device=page.device,
                        sha256=sha,
                        extra={"url": page.url, "scale": round(scale, 4)},
                    )
                )
                empty += not labels
                for element in labels:
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
        "devices": list(devices),
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
    parser.add_argument("--limit", type=int)
    args = parser.parse_args()
    stats = build_split(
        args.pages, args.data_root, args.split, args.out, DESKTOP_DEVICES, args.workers, args.limit
    )
    print(json.dumps(stats, indent=2))


if __name__ == "__main__":
    main()
