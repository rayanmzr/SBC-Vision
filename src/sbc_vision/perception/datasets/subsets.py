"""Sous-ensembles figés d'un corpus, communs à toutes les approches.

Une page WebUI existe en plusieurs résolutions quasi identiques, et un site en plusieurs pages
(la validation compte 5 615 pages pour 1 763 domaines). Un sous-ensemble d'évaluation garde une
seule capture par domaine, tirée avec une graine fixe : les mesures portent sur des sites
différents, et le bootstrap rééchantillonne des sites entiers.
"""

import random
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path

from sbc_vision.perception.datasets.near_duplicates import near_duplicate_groups
from sbc_vision.perception.datasets.records import ImageRecord, read_manifest


def one_per_group(
    records: Sequence[ImageRecord],
    count: int | None,
    seed: int = 0,
    key: str = "domain",
    exclude: set[str] = frozenset(),
) -> list[ImageRecord]:
    """Une capture par valeur de `key` (`domain` ou `group`), hors pages listées dans `exclude`."""
    by_group: dict[str, list[ImageRecord]] = {}
    for record in records:
        if record.group not in exclude:
            by_group.setdefault(getattr(record, key), []).append(record)
    rng = random.Random(seed)
    groups = sorted(by_group)
    rng.shuffle(groups)
    if count is not None:
        groups = groups[:count]
    picked = [rng.choice(sorted(by_group[g], key=lambda r: r.file_name)) for g in groups]
    return sorted(picked, key=lambda r: r.image_id)


@dataclass(frozen=True)
class EvaluationSubset:
    records: list[ImageRecord]
    pages_excluded: int  # quasi-doublons de l'entraînement écartés avant le tirage


def evaluation_subset(
    corpus: Path,
    split: str,
    count: int | None,
    seed: int = 0,
    near_duplicate_max: int | None = None,
    one_per: str = "domain",
) -> EvaluationSubset:
    """Une capture par site (`domain`) ou par page (`group`), quasi-doublons de l'entraînement
    écartés si `near_duplicate_max`."""
    excluded = (
        near_duplicate_groups(corpus, split, near_duplicate_max)
        if near_duplicate_max is not None
        else set()
    )
    records = read_manifest(corpus / f"{split}.manifest.jsonl")
    return EvaluationSubset(
        one_per_group(records, count, seed, key=one_per, exclude=excluded), len(excluded)
    )
