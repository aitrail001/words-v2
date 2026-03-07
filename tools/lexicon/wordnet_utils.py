from __future__ import annotations

from typing import Any, Callable, Iterable

from tools.lexicon.errors import LexiconDependencyError

CanonicalSense = dict[str, Any]
CanonicalSenseProvider = Callable[[str], Iterable[CanonicalSense]]

_POS_MAP = {
    'n': 'noun',
    'v': 'verb',
    'a': 'adjective',
    's': 'adjective',
    'r': 'adverb',
}


def select_learner_senses(
    canonical_senses: Iterable[CanonicalSense],
    *,
    max_senses: int = 4,
) -> list[CanonicalSense]:
    senses = list(canonical_senses)
    return senses[:max_senses]


def fallback_sense(word: str) -> CanonicalSense:
    return {
        'wn_synset_id': None,
        'part_of_speech': 'noun',
        'canonical_gloss': f'A learner-relevant meaning for {word}.',
        'canonical_label': word,
    }


def _wordnet_missing_message() -> str:
    return (
        'WordNet corpus is unavailable. Install `tools/lexicon/requirements.txt` and run '
        '`python3 -m nltk.downloader wordnet omw-1.4` before using `build-base`.'
    )


def _load_wordnet():
    try:
        from nltk.corpus import wordnet as wn
    except ModuleNotFoundError as exc:
        raise LexiconDependencyError(
            'NLTK WordNet support is unavailable. Install `tools/lexicon/requirements.txt` before using `build-base`.'
        ) from exc

    try:
        wn.ensure_loaded()
    except LookupError as exc:
        raise LexiconDependencyError(_wordnet_missing_message()) from exc
    return wn


def build_wordnet_sense_provider() -> CanonicalSenseProvider:
    wn = _load_wordnet()

    def provider(word: str) -> list[CanonicalSense]:
        senses: list[CanonicalSense] = []
        seen_synsets: set[str] = set()
        for synset in wn.synsets(word):
            synset_id = synset.name()
            if synset_id in seen_synsets:
                continue
            seen_synsets.add(synset_id)
            lemma_names = synset.lemma_names()
            canonical_label = (lemma_names[0] if lemma_names else word).replace('_', ' ')
            senses.append(
                {
                    'wn_synset_id': synset_id,
                    'part_of_speech': _POS_MAP.get(synset.pos(), 'noun'),
                    'canonical_gloss': synset.definition(),
                    'canonical_label': canonical_label,
                }
            )
        senses.sort(key=lambda item: str(item.get('wn_synset_id') or ''))
        return senses

    return provider
