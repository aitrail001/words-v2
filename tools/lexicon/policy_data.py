from __future__ import annotations

from functools import lru_cache
import json
from pathlib import Path

from tools.lexicon.wordfreq_utils import normalize_word_candidate


_ENTITY_CATEGORIES_PATH = Path(__file__).resolve().parent / "data" / "entity_categories.json"
_TAIL_EXCLUSIONS_PATH = Path(__file__).resolve().parent / "data" / "tail_exclusions.json"

ALLOWED_ENTITY_CATEGORIES = {"general", "name", "place", "brand", "entity_other"}


def _normalize_word_map(payload: dict[str, object]) -> dict[str, dict[str, str]]:
    normalized: dict[str, dict[str, str]] = {}
    for word, metadata in payload.items():
        normalized_word = normalize_word_candidate(str(word))
        if not normalized_word:
            continue
        row = dict(metadata or {})
        normalized[normalized_word] = {
            "reason": str(row.get("reason") or ""),
        }
    return normalized


@lru_cache(maxsize=1)
def load_entity_categories() -> dict[str, dict[str, dict[str, str]]]:
    if not _ENTITY_CATEGORIES_PATH.exists():
        return {category: {} for category in sorted(ALLOWED_ENTITY_CATEGORIES - {"general"})}
    payload = json.loads(_ENTITY_CATEGORIES_PATH.read_text(encoding="utf-8"))
    categories: dict[str, dict[str, dict[str, str]]] = {}
    for category in sorted(ALLOWED_ENTITY_CATEGORIES - {"general"}):
        categories[category] = _normalize_word_map(dict(payload.get(category) or {}))
    return categories


def resolve_entity_category(word: str) -> tuple[str, str | None]:
    normalized_word = normalize_word_candidate(word)
    if not normalized_word:
        return "general", None
    for category, entries in load_entity_categories().items():
        if normalized_word in entries:
            reason = str(entries[normalized_word].get("reason") or "").strip() or None
            return category, reason
    return "general", None


@lru_cache(maxsize=1)
def load_tail_exclusions() -> dict[str, dict[str, str]]:
    if not _TAIL_EXCLUSIONS_PATH.exists():
        return {}
    payload = json.loads(_TAIL_EXCLUSIONS_PATH.read_text(encoding="utf-8"))
    return _normalize_word_map(dict(payload.get("drop_canonical_forms") or {}))


def excluded_canonical_forms() -> set[str]:
    return set(load_tail_exclusions())


def tail_exclusion_reason(word: str) -> str | None:
    normalized_word = normalize_word_candidate(word)
    if not normalized_word:
        return None
    reason = str((load_tail_exclusions().get(normalized_word) or {}).get("reason") or "").strip()
    return reason or None
