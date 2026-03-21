"""Inventory helpers for lexicon offline runs."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Iterable
import re

from tools.lexicon.jsonl_io import read_jsonl
from tools.lexicon.wordfreq_utils import normalize_word_candidate


def normalize_surface_text(raw_text: str) -> str | None:
    text = str(raw_text or "").strip()
    if not text:
        return None
    text = re.sub(r"\s+", " ", text)
    return text.lower()


def build_seed_inventory(items: Iterable[str]) -> list[str]:
    normalized: list[str] = []
    seen: set[str] = set()
    for raw_item in items:
        item = normalize_surface_text(raw_item)
        if not item or item in seen:
            continue
        seen.add(item)
        normalized.append(item)
    return normalized


def build_word_seed_inventory(items: Iterable[str]) -> list[str]:
    normalized: list[str] = []
    seen: set[str] = set()
    for raw_item in items:
        item = normalize_word_candidate(raw_item)
        if not item or item in seen:
            continue
        seen.add(item)
        normalized.append(item)
    return normalized


def load_seed_rows(path: Path) -> list[dict[str, Any]]:
    return [dict(row) for row in read_jsonl(path)]
