from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Iterable, Optional

from tools.lexicon.ids import make_concept_id, make_lexeme_id, make_sense_id
from tools.lexicon.jsonl_io import write_jsonl
from tools.lexicon.models import ConceptRecord, LexemeRecord, SenseRecord
from tools.lexicon.wordfreq_utils import resolve_frequency_rank
from tools.lexicon.wordnet_utils import fallback_sense, select_learner_senses

CanonicalSenseProvider = Callable[[str], Iterable[dict[str, object]]]
RankProvider = Callable[[str], Optional[int]]


@dataclass(frozen=True)
class BaseBuildResult:
    lexemes: list[LexemeRecord]
    senses: list[SenseRecord]
    concepts: list[ConceptRecord]


def normalize_seed_words(words: Iterable[str]) -> list[str]:
    normalized: list[str] = []
    seen: set[str] = set()
    for raw_word in words:
        word = raw_word.strip().lower()
        if not word or word in seen:
            continue
        seen.add(word)
        normalized.append(word)
    return normalized


def build_base_records(
    *,
    words: Iterable[str],
    snapshot_id: str,
    created_at: str,
    rank_provider: RankProvider,
    sense_provider: CanonicalSenseProvider,
    max_senses: int = 8,
) -> BaseBuildResult:
    lexeme_records: list[LexemeRecord] = []
    sense_records: list[SenseRecord] = []
    concept_records: list[ConceptRecord] = []

    for word in normalize_seed_words(words):
        lexeme_id = make_lexeme_id(word)
        available_senses = list(sense_provider(word))
        canonical_senses = list(select_learner_senses(available_senses, max_senses=max_senses))
        is_wordnet_backed = bool(canonical_senses)
        if not canonical_senses:
            canonical_senses = [fallback_sense(word)]

        lexeme_records.append(
            LexemeRecord(
                snapshot_id=snapshot_id,
                lexeme_id=lexeme_id,
                lemma=word,
                language='en',
                wordfreq_rank=resolve_frequency_rank(word, rank_provider),
                is_wordnet_backed=is_wordnet_backed,
                source_refs=['wordnet', 'wordfreq'] if is_wordnet_backed else ['wordfreq'],
                created_at=created_at,
            )
        )

        is_high_polysemy = len(available_senses) > len(canonical_senses)
        for index, canonical_sense in enumerate(canonical_senses, start=1):
            wn_synset_id = canonical_sense.get('wn_synset_id')
            part_of_speech = str(canonical_sense.get('part_of_speech') or 'noun')
            canonical_gloss = str(canonical_sense.get('canonical_gloss') or f'A learner-relevant meaning for {word}.')
            canonical_label = str(canonical_sense.get('canonical_label') or word)

            sense_records.append(
                SenseRecord(
                    snapshot_id=snapshot_id,
                    sense_id=make_sense_id(lexeme_id, index),
                    lexeme_id=lexeme_id,
                    wn_synset_id=str(wn_synset_id) if wn_synset_id else None,
                    part_of_speech=part_of_speech,
                    canonical_gloss=canonical_gloss,
                    selection_reason='selected canonical learner sense' if is_wordnet_backed else 'fallback learner sense',
                    sense_order=index,
                    is_high_polysemy=is_high_polysemy,
                    created_at=created_at,
                )
            )

            if wn_synset_id:
                concept_records.append(
                    ConceptRecord(
                        snapshot_id=snapshot_id,
                        concept_id=make_concept_id(str(wn_synset_id)),
                        wn_synset_id=str(wn_synset_id),
                        canonical_label=canonical_label,
                        part_of_speech=part_of_speech,
                        gloss=canonical_gloss,
                        lemma_ids=[lexeme_id],
                        created_at=created_at,
                    )
                )

    return BaseBuildResult(
        lexemes=lexeme_records,
        senses=sense_records,
        concepts=concept_records,
    )


def write_base_snapshot(output_dir: Path, result: BaseBuildResult) -> dict[str, Path]:
    output_dir.mkdir(parents=True, exist_ok=True)
    paths = {
        'lexemes': output_dir / 'lexemes.jsonl',
        'senses': output_dir / 'senses.jsonl',
        'concepts': output_dir / 'concepts.jsonl',
    }
    write_jsonl(paths['lexemes'], [record.to_dict() for record in result.lexemes])
    write_jsonl(paths['senses'], [record.to_dict() for record in result.senses])
    write_jsonl(paths['concepts'], [record.to_dict() for record in result.concepts])
    return paths
