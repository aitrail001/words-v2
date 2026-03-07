from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any


@dataclass(frozen=True)
class SerializableRecord:
    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class SenseExample(SerializableRecord):
    sentence: str
    difficulty: str


@dataclass(frozen=True)
class LexemeRecord(SerializableRecord):
    snapshot_id: str
    lexeme_id: str
    lemma: str
    language: str
    wordfreq_rank: int
    is_wordnet_backed: bool
    source_refs: list[str]
    created_at: str


@dataclass(frozen=True)
class SenseRecord(SerializableRecord):
    snapshot_id: str
    sense_id: str
    lexeme_id: str
    wn_synset_id: str | None
    part_of_speech: str
    canonical_gloss: str
    selection_reason: str
    sense_order: int
    is_high_polysemy: bool
    created_at: str


@dataclass(frozen=True)
class ConceptRecord(SerializableRecord):
    snapshot_id: str
    concept_id: str
    wn_synset_id: str | None
    canonical_label: str
    part_of_speech: str
    gloss: str
    lemma_ids: list[str]
    created_at: str


@dataclass(frozen=True)
class EnrichmentRecord(SerializableRecord):
    snapshot_id: str
    enrichment_id: str
    sense_id: str
    definition: str
    examples: list[SenseExample]
    cefr_level: str
    primary_domain: str
    secondary_domains: list[str]
    register: str
    synonyms: list[str]
    antonyms: list[str]
    collocations: list[str]
    grammar_patterns: list[str]
    usage_note: str
    forms: dict[str, Any]
    confusable_words: list[dict[str, str]]
    model_name: str
    prompt_version: str
    generation_run_id: str
    confidence: float
    review_status: str
    generated_at: str


@dataclass(frozen=True)
class ExpressionRecord(SerializableRecord):
    snapshot_id: str
    expression_id: str
    expression_text: str
    expression_type: str
    linked_lexeme_ids: list[str]
    linked_concept_ids: list[str]
    base_definition: str
    enrichment_ref: str
    source_type: str
    created_at: str


@dataclass(frozen=True)
class CompiledWordRecord(SerializableRecord):
    schema_version: str
    word: str
    part_of_speech: list[str]
    cefr_level: str
    frequency_rank: int
    forms: dict[str, Any]
    senses: list[dict[str, Any]]
    confusable_words: list[dict[str, str]]
    generated_at: str
