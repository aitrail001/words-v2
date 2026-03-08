from __future__ import annotations

import math
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

_POS_WEIGHTS = {
    'verb': 28.0,
    'noun': 18.0,
    'adjective': 12.0,
    'adverb': 6.0,
}
_GENERAL_GLOSS_KEYWORDS = {
    'move', 'moving', 'foot', 'place', 'put', 'operate', 'function', 'manage', 'conduct',
    'guide', 'prepare', 'group', 'collection', 'belong', 'person', 'activity', 'use',
    'make', 'happen', 'important', 'principal', 'ready', 'position', 'race', 'event',
    'act', 'together', 'front', 'competition', 'team', 'business', 'test', 'trial',
    'role', 'actor', 'story', 'children', 'playful', 'general', 'everyday', 'work',
    'device', 'source', 'discussion', 'topic', 'question', 'problem', 'document',
    'information', 'institution', 'money', 'meal', 'food', 'furniture', 'plan', 'gift',
    'amount', 'price', 'direction', 'side', 'weight', 'color', 'shape', 'knowledge',
    'separate', 'piece', 'pieces', 'broken', 'opening', 'open', 'closed', 'shut', 'access',
    'public', 'community', 'shared', 'widely', 'known', 'encountered', 'payment', 'goods', 'services',
    'container', 'carry', 'records', 'record', 'financial', 'deposit', 'deposits', 'lending', 'current', 'now', 'gift',
}
_SPECIALIZED_GLOSS_KEYWORDS = {
    'baseball', 'cricket', 'mathematics', 'mathematical', 'theater', 'theatre', 'film',
    'chemistry', 'chemical', 'physics', 'linguistics', 'grammar', 'metallic', 'metal',
    'toxic', 'scientific', 'score', 'scoring', 'gun', 'missile', 'piston', 'engine',
    'egyptian', 'osiris', 'tennis', 'squash', 'radio', 'tv', 'psychology',
    'logic', 'architecture', 'biology', 'celestial', 'planet', 'planets', 'sun', 'earth', 'encumbrance',
    'tournament', 'amateur', 'amateurs', 'professional', 'professionals', 'urban', 'recreational', 'target',
    'football', 'teammate', 'sports', 'gambling', 'banker', 'hebrew', 'diacritics', 'geometric', 'gospel', 'apostle', 'saint', 'genesis', 'debutante', 'lathe',
}
_ABSTRACT_GLOSS_KEYWORDS = {
    'relation', 'condition', 'state', 'process', 'system', 'property', 'class', 'concept',
    'abstraction', 'quality', 'measure', 'instance', 'kind', 'tendency', 'disposition',
}
_LOW_VALUE_GLOSS_KEYWORDS = {
    'submissive', 'obedient', 'useful', 'utility', 'discipline', 'punish', 'punishment', 'control', 'crack', 'cracks', 'chink', 'chinks', 'surface', 'infamy',
}
_INSTITUTIONAL_GLOSS_KEYWORDS = {
    'court', 'law', 'legal', 'military', 'religious', 'government', 'official', 'public office', 'warrant', 'nation', 'administrative district',
}
_ARCHAIC_GLOSS_KEYWORDS = {
    'formerly',
}
_BODY_PART_GLOSS_KEYWORDS = {
    'mouth', 'eye', 'eyes', 'ear', 'ears', 'lip', 'lips', 'eyelid', 'eyelids',
}
_MEASUREMENT_GLOSS_KEYWORDS = {
    'measure', 'measurement', 'standard', 'magnitude', 'range', 'compare', 'comparison',
}
_CONFLICT_GLOSS_KEYWORDS = {
    'attack', 'rush', 'violent', 'violently',
}
_CAUSATIVE_PATTERNS = (
    'cause to ',
    'cause something to ',
    'cause an animal to ',
    'cause a person to ',
    'have as a result',
    'tend to or result in',
    'be conducive to',
    'direct or control',
    'cause to emit',
    'cause to perform',
)
_DERIVED_NOUN_PATTERNS = (
    'the act of ',
    'an act of ',
    'the action of ',
)
_COMPETITIVE_NONVERB_SCORE = 30.0
_DIVERSITY_BONUS = 14.0
_LEMMA_COUNT_SCALE = {
    'verb': 1.5,
    'noun': 2.6,
    'adjective': 2.2,
    'adverb': 1.5,
}
_LEMMA_COUNT_CAP = {
    'verb': 6.0,
    'noun': 12.0,
    'adjective': 9.0,
    'adverb': 6.0,
}
_POS_VIABILITY_RULES = {
    'adjective': {'min_count': 12, 'min_ratio': 0.35, 'max_margin': 14.0, 'selection_bonus': 12.0},
    'adverb': {'min_count': 10, 'min_ratio': 0.30, 'max_margin': 10.0, 'selection_bonus': 8.0},
}
_SELECTION_BUCKETS = (4, 6, 8)


def _normalized_gloss(sense: CanonicalSense) -> str:
    return str(sense.get('canonical_gloss') or '').lower()


def _keyword_hits(gloss: str, keywords: set[str]) -> int:
    return sum(1 for keyword in keywords if keyword in gloss)


def _is_specialized_sense(sense: CanonicalSense) -> bool:
    gloss = _normalized_gloss(sense)
    return _keyword_hits(gloss, _SPECIALIZED_GLOSS_KEYWORDS) > 0


def _lemma_count(sense: CanonicalSense) -> int:
    try:
        return max(0, int(sense.get('lemma_count') or 0))
    except (TypeError, ValueError):
        return 0


def _query_lemma(sense: CanonicalSense) -> str:
    return str(sense.get('query_lemma') or '').strip().lower()


def _canonical_label(sense: CanonicalSense) -> str:
    return str(sense.get('canonical_label') or '').strip().lower()


def _canonical_label_affinity_penalty(sense: CanonicalSense) -> float:
    query = _query_lemma(sense)
    label = _canonical_label(sense)
    if not query or not label:
        return 0.0
    if label == query:
        return 0.0
    if query in label:
        return 6.0
    return 16.0


def _lemma_frequency_bonus(sense: CanonicalSense) -> float:
    part_of_speech = str(sense.get('part_of_speech') or 'noun')
    count = _lemma_count(sense)
    if count <= 0:
        return 0.0

    gloss = _normalized_gloss(sense)
    scale = _LEMMA_COUNT_SCALE.get(part_of_speech, 1.5)
    cap = _LEMMA_COUNT_CAP.get(part_of_speech, 6.0)
    bonus = min(cap, math.log2(count + 1) * scale)

    specialized_hits = _keyword_hits(gloss, _SPECIALIZED_GLOSS_KEYWORDS)
    abstract_hits = _keyword_hits(gloss, _ABSTRACT_GLOSS_KEYWORDS)
    if specialized_hits > 0:
        bonus *= 0.35
    elif abstract_hits > 0:
        bonus *= 0.7
    return bonus


def _has_strong_verb_candidate(canonical_senses: list[CanonicalSense]) -> bool:
    for sense in canonical_senses:
        if str(sense.get('part_of_speech') or 'noun') != 'verb':
            continue
        gloss = _normalized_gloss(sense)
        if not any(gloss.startswith(pattern) for pattern in _CAUSATIVE_PATTERNS):
            return True
    return False


def _sense_score(sense: CanonicalSense, original_index: int, *, strong_verb_exists: bool = False) -> float:
    gloss = _normalized_gloss(sense)
    part_of_speech = str(sense.get('part_of_speech') or 'noun')
    score = _POS_WEIGHTS.get(part_of_speech, 0.0)
    score += min(3, _keyword_hits(gloss, _GENERAL_GLOSS_KEYWORDS)) * 5.0
    score += _lemma_frequency_bonus(sense)
    score += min(2, _keyword_hits(gloss, _MEASUREMENT_GLOSS_KEYWORDS)) * (7.0 if part_of_speech == 'noun' else 3.0)
    score -= min(3, _keyword_hits(gloss, _SPECIALIZED_GLOSS_KEYWORDS)) * 12.0
    score -= min(2, _keyword_hits(gloss, _ABSTRACT_GLOSS_KEYWORDS)) * 8.0
    score -= min(2, _keyword_hits(gloss, _LOW_VALUE_GLOSS_KEYWORDS)) * 9.0
    score -= min(2, _keyword_hits(gloss, _INSTITUTIONAL_GLOSS_KEYWORDS)) * 6.0
    score -= min(1, _keyword_hits(gloss, _ARCHAIC_GLOSS_KEYWORDS)) * 8.0
    score -= min(2, _keyword_hits(gloss, _CONFLICT_GLOSS_KEYWORDS)) * 10.0
    score -= _canonical_label_affinity_penalty(sense)
    if part_of_speech == 'adjective' and _keyword_hits(gloss, _BODY_PART_GLOSS_KEYWORDS) > 0:
        score -= 8.0
    if any(gloss.startswith(pattern) for pattern in _CAUSATIVE_PATTERNS):
        score -= 12.0
    if part_of_speech == 'noun' and strong_verb_exists and any(gloss.startswith(pattern) for pattern in _DERIVED_NOUN_PATTERNS):
        score -= 18.0
    score -= original_index * 0.01
    return score


def rank_learner_sense_candidates(canonical_senses: Iterable[CanonicalSense]) -> list[dict[str, Any]]:
    senses = list(canonical_senses)
    strong_verb_exists = _has_strong_verb_candidate(senses)
    ranked_senses = [
        {
            'index': index,
            'sense': sense,
            'pos': str(sense.get('part_of_speech') or 'noun'),
            'score': _sense_score(sense, index, strong_verb_exists=strong_verb_exists),
            'specialized': _is_specialized_sense(sense),
        }
        for index, sense in enumerate(senses)
    ]
    ranked_senses.sort(key=lambda item: item['score'], reverse=True)
    return ranked_senses


def _adaptive_target_count(ranked_senses: list[dict[str, Any]], *, max_senses: int) -> int:
    if not ranked_senses:
        return 0
    ceiling = max(1, max_senses)
    available = len(ranked_senses)
    base_target = min(4, ceiling, available)
    if ceiling <= 4:
        return base_target

    scores = [item['score'] for item in ranked_senses]
    competitive_nonverbs = sum(1 for item in ranked_senses if item['pos'] != 'verb' and item['score'] >= _COMPETITIVE_NONVERB_SCORE)

    if ceiling >= 8 and available >= 8 and len(scores) >= 8 and scores[6] >= 35.0 and scores[7] >= 35.0 and competitive_nonverbs >= 2:
        return 8
    if ceiling >= 6 and available >= 6 and len(scores) >= 6 and scores[3] >= 30.0 and scores[5] >= 20.0:
        return 6
    return base_target


def _lemma_count_by_pos(ranked_senses: list[dict[str, Any]]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for item in ranked_senses:
        counts[item['pos']] = counts.get(item['pos'], 0) + _lemma_count(item['sense'])
    return counts


def _viable_uncovered_pos_candidates(
    ranked_senses: list[dict[str, Any]],
    *,
    target_count: int,
) -> dict[int, float]:
    if not ranked_senses or target_count <= 0:
        return {}

    counts_by_pos = _lemma_count_by_pos(ranked_senses)
    max_pos_count = max(counts_by_pos.values(), default=0)
    if max_pos_count <= 0:
        return {}

    covered_pos = {item['pos'] for item in ranked_senses[:target_count]}
    cutoff_score = ranked_senses[min(target_count, len(ranked_senses)) - 1]['score']
    bonuses: dict[int, float] = {}

    for pos, rules in _POS_VIABILITY_RULES.items():
        if pos in covered_pos:
            continue
        pos_count = counts_by_pos.get(pos, 0)
        if pos_count < int(rules['min_count']):
            continue
        if pos_count < max_pos_count * float(rules['min_ratio']):
            continue

        candidate = next(
            (
                item for item in ranked_senses
                if item['pos'] == pos and not item['specialized']
            ),
            None,
        )
        if candidate is None:
            continue

        margin = cutoff_score - candidate['score']
        if margin < 0 or margin > float(rules['max_margin']):
            continue
        bonuses[candidate['index']] = float(rules['selection_bonus'])

    return bonuses


def _expand_target_count_for_viable_pos(
    ranked_senses: list[dict[str, Any]],
    *,
    target_count: int,
    max_senses: int,
    viable_bonus_indexes: dict[int, float],
) -> int:
    if not viable_bonus_indexes:
        return target_count

    available = len(ranked_senses)
    ceiling = max(1, max_senses)
    expanded = target_count
    for bucket in _SELECTION_BUCKETS:
        if expanded < bucket <= ceiling and available >= bucket:
            return bucket
    return min(available, ceiling, expanded + len(viable_bonus_indexes))


def _effective_selection_score(
    item: dict[str, Any],
    selected: list[dict[str, Any]],
    *,
    viable_bonus_indexes: dict[int, float],
) -> float:
    score = item['score']
    selected_pos = {chosen['pos'] for chosen in selected}
    same_pos_count = sum(1 for chosen in selected if chosen['pos'] == item['pos'])
    if item['pos'] not in selected_pos and item['score'] >= _COMPETITIVE_NONVERB_SCORE:
        score += _DIVERSITY_BONUS
    if same_pos_count >= 2:
        score -= same_pos_count * 4.0
    if item['index'] in viable_bonus_indexes and item['pos'] not in selected_pos:
        score += viable_bonus_indexes[item['index']]
    return score


def select_learner_senses(
    canonical_senses: Iterable[CanonicalSense],
    *,
    max_senses: int = 8,
) -> list[CanonicalSense]:
    ranked_senses = rank_learner_sense_candidates(canonical_senses)

    target_count = _adaptive_target_count(ranked_senses, max_senses=max_senses)
    if target_count <= 0:
        return []

    viable_bonus_indexes = _viable_uncovered_pos_candidates(ranked_senses, target_count=target_count)
    target_count = _expand_target_count_for_viable_pos(
        ranked_senses,
        target_count=target_count,
        max_senses=max_senses,
        viable_bonus_indexes=viable_bonus_indexes,
    )

    selected: list[dict[str, Any]] = []
    selected_indexes: set[int] = set()

    while len(selected) < target_count:
        remaining = [item for item in ranked_senses if item['index'] not in selected_indexes]
        if not remaining:
            break

        specialized_in_first_four = sum(1 for item in selected[:4] if item['specialized'])
        candidates = []
        for item in remaining:
            if len(selected) < min(4, target_count) and specialized_in_first_four >= 1 and item['specialized']:
                continue
            candidates.append((
                _effective_selection_score(item, selected, viable_bonus_indexes=viable_bonus_indexes),
                item,
            ))
        if not candidates:
            candidates = [
                (_effective_selection_score(item, selected, viable_bonus_indexes=viable_bonus_indexes), item)
                for item in remaining
            ]

        candidates.sort(key=lambda pair: (pair[0], pair[1]['score']), reverse=True)
        candidate = candidates[0][1]
        selected.append(candidate)
        selected_indexes.add(candidate['index'])

    return [item['sense'] for item in selected]


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
        normalized_word = word.replace('_', ' ').lower()
        for synset in wn.synsets(word):
            synset_id = synset.name()
            if synset_id in seen_synsets:
                continue
            seen_synsets.add(synset_id)
            lemma_names = synset.lemma_names()
            canonical_label = (lemma_names[0] if lemma_names else word).replace('_', ' ')
            lemma_count = max(
                (
                    lemma.count()
                    for lemma in synset.lemmas()
                    if lemma.name().replace('_', ' ').lower() == normalized_word
                ),
                default=0,
            )
            senses.append(
                {
                    'wn_synset_id': synset_id,
                    'part_of_speech': _POS_MAP.get(synset.pos(), 'noun'),
                    'canonical_gloss': synset.definition(),
                    'canonical_label': canonical_label,
                    'lemma_count': lemma_count,
                    'query_lemma': normalized_word,
                }
            )
        return senses

    return provider
