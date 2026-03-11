from __future__ import annotations

from typing import Callable, Iterable, Optional

from tools.lexicon.errors import LexiconDependencyError

RankProvider = Callable[[str], Optional[int]]
InventoryProvider = Callable[[int], Iterable[str]]


def resolve_frequency_rank(word: str, provider: RankProvider) -> int:
    rank = provider(word)
    if rank is None or rank <= 0:
        return 999_999
    return int(rank)


def normalize_word_candidate(raw_word: str) -> str | None:
    word = str(raw_word or '').strip().lower()
    if not word:
        return None
    if any(char.isspace() for char in word):
        return None
    if any(char.isdigit() for char in word):
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
