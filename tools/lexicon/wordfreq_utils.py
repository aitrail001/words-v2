from __future__ import annotations

from functools import lru_cache
import json
from pathlib import Path
from typing import Callable, Iterable, Optional

from tools.lexicon.errors import LexiconDependencyError

RankProvider = Callable[[str], Optional[int]]
InventoryProvider = Callable[[int], Iterable[str]]
_SURFACE_FORM_OVERRIDES_PATH = Path(__file__).resolve().parent / "data" / "surface_form_overrides.json"


@lru_cache(maxsize=1)
def _load_surface_form_overrides() -> dict[str, object]:
    if not _SURFACE_FORM_OVERRIDES_PATH.exists():
        return {
            "drop_surface_forms": [],
            "normalize_surface_forms": {},
        }
    payload = json.loads(_SURFACE_FORM_OVERRIDES_PATH.read_text(encoding="utf-8"))
    return {
        "drop_surface_forms": sorted(
            {
                str(word).strip().lower()
                for word in (payload.get("drop_surface_forms") or [])
                if str(word).strip()
            }
        ),
        "normalize_surface_forms": {
            str(source).strip().lower(): str(target).strip().lower()
            for source, target in dict(payload.get("normalize_surface_forms") or {}).items()
            if str(source).strip() and str(target).strip()
        },
    }


def resolve_frequency_rank(word: str, provider: RankProvider) -> int:
    rank = provider(word)
    if rank is None or rank <= 0:
        return 999_999
    return int(rank)


def normalize_word_candidate(raw_word: str) -> str | None:
    word = str(raw_word or '').strip().lower()
    if not word:
        return None
    overrides = _load_surface_form_overrides()
    if word in set(overrides.get("drop_surface_forms") or []):
        return None
    normalized_overrides = dict(overrides.get("normalize_surface_forms") or {})
    if word in normalized_overrides:
        word = normalized_overrides[word]
    if any(char.isspace() for char in word):
        return None
    if any(char.isdigit() for char in word):
        return None
    if len(word) == 3 and word[0].isalpha() and word[1:] == "'s":
        return None
    if not word[0].isalpha() or not word[-1].isalpha():
        return None
    for index, char in enumerate(word):
        if char.isalpha():
            continue
        if char not in {"'", "-"}:
            return None
        if index == 0 or index == len(word) - 1:
            return None
        prev_char = word[index - 1]
        next_char = word[index + 1]
        if not prev_char.isalpha() or not next_char.isalpha():
            return None
    return word


def build_wordfreq_rank_provider(language: str = 'en') -> RankProvider:
    try:
        from wordfreq import zipf_frequency
    except ModuleNotFoundError as exc:
        raise LexiconDependencyError(
            'wordfreq is unavailable. Install `tools/lexicon/requirements.txt` before using `build-base`.'
        ) from exc

    def provider(word: str) -> Optional[int]:
        zipf = float(zipf_frequency(word, language, wordlist='best'))
        if zipf <= 0:
            return None
        return max(1, int(round((8.0 - zipf) * 100_000)))

    return provider


def build_wordfreq_inventory_provider(language: str = 'en') -> InventoryProvider:
    try:
        from wordfreq import top_n_list
    except ModuleNotFoundError as exc:
        raise LexiconDependencyError(
            'wordfreq is unavailable. Install `tools/lexicon/requirements.txt` before using `build-base`.'
        ) from exc

    def provider(limit: int) -> Iterable[str]:
        return top_n_list(language, int(limit))

    return provider
