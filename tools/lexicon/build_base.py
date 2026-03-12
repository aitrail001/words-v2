from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Iterable, Optional

from tools.lexicon.canonical_forms import canonicalize_words
from tools.lexicon.ids import make_concept_id, make_lexeme_id, make_sense_id
from tools.lexicon.jsonl_io import write_jsonl
from tools.lexicon.models import (
    CanonicalEntryRecord,
    CanonicalVariantRecord,
    ConceptRecord,
    GenerationStatusRecord,
    LexemeRecord,
    SenseRecord,
)
from tools.lexicon.wordfreq_utils import InventoryProvider, normalize_word_candidate, resolve_frequency_rank
from tools.lexicon.wordnet_utils import fallback_sense, select_learner_senses

CanonicalSenseProvider = Callable[[str], Iterable[dict[str, object]]]
RankProvider = Callable[[str], Optional[int]]


@dataclass(frozen=True)
class BaseBuildResult:
    lexemes: list[LexemeRecord]
    senses: list[SenseRecord]
    concepts: list[ConceptRecord]
    canonical_entries: list[CanonicalEntryRecord]
    canonical_variants: list[CanonicalVariantRecord]
    generation_status: list[GenerationStatusRecord]


def normalize_seed_words(words: Iterable[str]) -> list[str]:
    normalized: list[str] = []
    seen: set[str] = set()
    for raw_word in words:
        word = normalize_word_candidate(raw_word)
        if not word or word in seen:
            continue
        seen.add(word)
        normalized.append(word)
    return normalized


def build_word_inventory(*, limit: int, inventory_provider: InventoryProvider) -> list[str]:
    return normalize_seed_words(inventory_provider(int(limit)))


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
    canonical_entry_records: list[CanonicalEntryRecord] = []
    canonical_variant_records: list[CanonicalVariantRecord] = []
    generation_status_records: list[GenerationStatusRecord] = []

    sense_cache: dict[str, list[dict[str, object]]] = {}

    def get_senses(word: str) -> list[dict[str, object]]:
        if word not in sense_cache:
            sense_cache[word] = list(sense_provider(word))
        return sense_cache[word]

    canonicalization = canonicalize_words(
        words=normalize_seed_words(words),
        rank_provider=rank_provider,
        sense_provider=get_senses,
    )

    source_forms_by_canonical: dict[str, list[str]] = {}
    linked_base_by_canonical: dict[str, str | None] = {}
    for decision in canonicalization.decisions:
        if decision.canonical_form not in source_forms_by_canonical:
            source_forms_by_canonical[decision.canonical_form] = []
        if decision.surface_form not in source_forms_by_canonical[decision.canonical_form]:
            source_forms_by_canonical[decision.canonical_form].append(decision.surface_form)
        if decision.linked_canonical_form and decision.canonical_form not in linked_base_by_canonical:
            linked_base_by_canonical[decision.canonical_form] = decision.linked_canonical_form
        canonical_variant_records.append(
            CanonicalVariantRecord(
                snapshot_id=snapshot_id,
                entry_id=make_lexeme_id(decision.canonical_form),
                surface_form=decision.surface_form,
                canonical_form=decision.canonical_form,
                decision=decision.decision,
                decision_reason=decision.decision_reason,
                confidence=decision.confidence,
                variant_type=decision.variant_type,
                linked_canonical_form=decision.linked_canonical_form,
                is_separately_learner_worthy=decision.is_separately_learner_worthy,
                created_at=created_at,
            )
        )

    for word in canonicalization.canonical_words:
        lexeme_id = make_lexeme_id(word)
        available_senses = get_senses(word)
        canonical_senses = list(select_learner_senses(available_senses, max_senses=max_senses))
        is_wordnet_backed = bool(canonical_senses)
        if not canonical_senses:
            canonical_senses = [fallback_sense(word)]

        source_provenance = [{"source": "wordfreq", "role": "frequency_rank"}]
        if is_wordnet_backed:
            source_provenance.append({"source": "wordnet", "role": "sense_grounding"})

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
                source_provenance=source_provenance,
            )
        )

        canonical_entry_records.append(
            CanonicalEntryRecord(
                snapshot_id=snapshot_id,
                entry_id=lexeme_id,
                canonical_form=word,
                display_form=word,
                normalized_form=word,
                source_forms=source_forms_by_canonical.get(word, [word]),
                linked_canonical_form=linked_base_by_canonical.get(word),
                created_at=created_at,
            )
        )
        generation_status_records.append(
            GenerationStatusRecord(
                snapshot_id=snapshot_id,
                entry_id=lexeme_id,
                canonical_form=word,
                updated_at=created_at,
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
        canonical_entries=canonical_entry_records,
        canonical_variants=canonical_variant_records,
        generation_status=generation_status_records,
    )


def write_base_snapshot(output_dir: Path, result: BaseBuildResult) -> dict[str, Path]:
    output_dir.mkdir(parents=True, exist_ok=True)
    paths = {
        'lexemes': output_dir / 'lexemes.jsonl',
        'senses': output_dir / 'senses.jsonl',
        'concepts': output_dir / 'concepts.jsonl',
        'canonical_entries': output_dir / 'canonical_entries.jsonl',
        'canonical_variants': output_dir / 'canonical_variants.jsonl',
        'generation_status': output_dir / 'generation_status.jsonl',
    }
    write_jsonl(paths['lexemes'], [record.to_dict() for record in result.lexemes])
    write_jsonl(paths['senses'], [record.to_dict() for record in result.senses])
    write_jsonl(paths['concepts'], [record.to_dict() for record in result.concepts])
    write_jsonl(paths['canonical_entries'], [record.to_dict() for record in result.canonical_entries])
    write_jsonl(paths['canonical_variants'], [record.to_dict() for record in result.canonical_variants])
    write_jsonl(paths['generation_status'], [record.to_dict() for record in result.generation_status])
    return paths
