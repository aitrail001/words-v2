from __future__ import annotations

from typing import Callable, Optional

from tools.lexicon.wordnet_provider import LexiconDependencyError


RankProvider = Callable[[str], Optional[int]]


def build_wordfreq_rank_provider(*, language: str = "en", max_rank: int = 250_000) -> RankProvider:
    try:
        from wordfreq import top_n_list
    except ImportError as exc:
        raise LexiconDependencyError(
            "wordfreq provider requires `wordfreq`. Install `tools/lexicon/requirements.txt` first."
        ) from exc

    rank_cache: dict[str, int] | None = None

    def provider(word: str) -> Optional[int]:
        nonlocal rank_cache
        if rank_cache is None:
            rank_cache = {
                item: index
                for index, item in enumerate(top_n_list(language, max_rank), start=1)
            }
        return rank_cache.get(word.lower())

    return provider
