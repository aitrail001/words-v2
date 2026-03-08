from __future__ import annotations

from typing import Callable


class LexiconDependencyError(RuntimeError):
    pass


SenseProvider = Callable[[str], list[dict[str, object]]]


_POS_MAP = {
    "n": "noun",
    "v": "verb",
    "a": "adjective",
    "s": "adjective",
    "r": "adverb",
}


def build_wordnet_sense_provider() -> SenseProvider:
    try:
        from nltk.corpus import wordnet as wn
    except ImportError as exc:
        raise LexiconDependencyError(
            "WordNet provider requires `nltk`. Install `tools/lexicon/requirements.txt` first."
        ) from exc

    try:
        wn.ensure_loaded()
    except LookupError as exc:
        raise LexiconDependencyError(
            "WordNet corpus is unavailable. Install NLTK data for `wordnet` before running `build-base`."
        ) from exc

    def provider(word: str) -> list[dict[str, object]]:
        senses: list[dict[str, object]] = []
        seen_synsets: set[str] = set()
        normalized_word = word.replace("_", " ").lower()
        for synset in wn.synsets(word):
            synset_id = synset.name()
            if synset_id in seen_synsets:
                continue
            seen_synsets.add(synset_id)
            lemma_names = synset.lemma_names()
            canonical_label = lemma_names[0].replace("_", " ") if lemma_names else word
            lemma_count = max(
                (
                    lemma.count()
                    for lemma in synset.lemmas()
                    if lemma.name().replace("_", " ").lower() == normalized_word
                ),
                default=0,
            )
            senses.append(
                {
                    "wn_synset_id": synset_id,
                    "part_of_speech": _POS_MAP.get(synset.pos(), "noun"),
                    "canonical_gloss": synset.definition(),
                    "canonical_label": canonical_label,
                    "lemma_count": lemma_count,
                    "query_lemma": normalized_word,
                }
            )
        return senses

    return provider
