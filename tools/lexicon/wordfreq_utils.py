from __future__ import annotations

from typing import Callable, Optional

from tools.lexicon.errors import LexiconDependencyError

RankProvider = Callable[[str], Optional[int]]


def resolve_frequency_rank(word: str, provider: RankProvider) -> int:
    rank = provider(word)
    if rank is None or rank <= 0:
        return 999_999
    return int(rank)


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
        # Monotonic approximation: more frequent words receive lower ranks.
        return max(1, int(round((8.0 - zipf) * 100_000)))

    return provider
