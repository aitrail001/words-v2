from __future__ import annotations

import hashlib
import re
from typing import Union


def _slugify(value: str) -> str:
    normalized = value.strip().lower().replace(".", "_")
    normalized = re.sub(r"[^a-z0-9_-]+", "_", normalized)
    normalized = re.sub(r"_+", "_", normalized).strip("_")
    return normalized


def _stable_suffix(value: str) -> str:
    return hashlib.blake2b(value.encode("utf-8"), digest_size=4).hexdigest()


def _slug_with_suffix(value: str) -> str:
    slug = _slugify(value) or "item"
    return f"{slug}_{_stable_suffix(value)}"


def build_snapshot_id(date_stamp: str, source_label: str) -> str:
    return f"lexicon-{_slugify(date_stamp)}-{_slugify(source_label)}"


def make_lexeme_id(lemma: str) -> str:
    return f"lx_{_slugify(lemma)}"


def make_sense_id(lexeme_id: str, sense_ref: Union[int, str]) -> str:
    if isinstance(sense_ref, int):
        return f"sn_{_slugify(lexeme_id)}_{sense_ref}"
    return f"sn_{_slugify(lexeme_id)}_{_slug_with_suffix(sense_ref)}"


def make_concept_id(wn_synset_id: str) -> str:
    return f"cp_{_slug_with_suffix(wn_synset_id)}"


def make_enrichment_id(sense_id: str, version: str) -> str:
    return f"en_{_slugify(sense_id)}_{_slugify(version)}"


def make_entry_id(entry_kind: str, value: str) -> str:
    kind = _slugify(entry_kind)
    prefix_map = {
        "phrase": "ph",
        "reference": "rf",
        "word": "lx",
    }
    prefix = prefix_map.get(kind, kind[:2] or "en")
    return f"{prefix}_{_slug_with_suffix(value)}"
