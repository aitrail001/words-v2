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
        for synset in wn.synsets(word):
            lemma_names = synset.lemma_names()
            canonical_label = lemma_names[0].replace("_", " ") if lemma_names else word
            senses.append(
                {
                    "wn_synset_id": synset.name(),
                    "part_of_speech": _POS_MAP.get(synset.pos(), "noun"),
                    "canonical_gloss": synset.definition(),
                    "canonical_label": canonical_label,
                }
            )
        return senses

    return provider
