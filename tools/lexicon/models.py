from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any


def _default_source_provenance(source_refs: list[str]) -> list[dict[str, Any]]:
    return [{"source": source} for source in source_refs]


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
    entry_id: str | None = None
    entry_type: str = "word"
    normalized_form: str | None = None
    source_provenance: list[dict[str, Any]] | None = None
    is_variant_with_distinct_meanings: bool = False
    variant_base_form: str | None = None
    variant_relationship: str | None = None
    entity_category: str = "general"

    def __post_init__(self) -> None:
        if self.entry_id is None:
            object.__setattr__(self, "entry_id", self.lexeme_id)
        if self.normalized_form is None:
            object.__setattr__(self, "normalized_form", self.lemma.strip().lower())
        if self.source_provenance is None:
            object.__setattr__(self, "source_provenance", _default_source_provenance(self.source_refs))


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
class CanonicalEntryRecord(SerializableRecord):
    snapshot_id: str
    entry_id: str
    canonical_form: str
    display_form: str
    normalized_form: str
    source_forms: list[str]
    created_at: str
    language: str = "en"
    entry_type: str = "word"
    linked_canonical_form: str | None = None
    notes: str | None = None


@dataclass(frozen=True)
class CanonicalVariantRecord(SerializableRecord):
    snapshot_id: str
    entry_id: str
    surface_form: str
    canonical_form: str
    decision: str
    decision_reason: str
    confidence: float
    variant_type: str
    created_at: str
    linked_canonical_form: str | None = None
    is_separately_learner_worthy: bool = False
    candidate_forms: list[str] | None = None
    ambiguity_reason: str | None = None
    needs_llm_adjudication: bool = False


@dataclass(frozen=True)
class AmbiguousFormRecord(SerializableRecord):
    surface_form: str
    deterministic_decision: str
    canonical_form: str
    linked_canonical_form: str | None
    candidate_forms: list[str]
    decision_reason: str
    confidence: float
    wordfreq_rank: int
    sense_labels: list[str]
    ambiguity_reason: str


@dataclass(frozen=True)
class FormAdjudicationRecord(SerializableRecord):
    surface_form: str
    selected_action: str
    selected_canonical_form: str
    selected_linked_canonical_form: str | None
    candidate_forms: list[str]
    model_name: str
    prompt_version: str
    generation_run_id: str
    confidence: float
    adjudication_reason: str


@dataclass(frozen=True)
class GenerationStatusRecord(SerializableRecord):
    snapshot_id: str
    entry_id: str
    canonical_form: str
    updated_at: str
    discovered: bool = True
    base_built: bool = True
    enriched: bool = False
    compiled: bool = False
    published: bool = False
    last_source_reference: str | None = None


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
    translations: dict[str, dict[str, Any]] | None = None


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
    entry_id: str | None = None
    entry_type: str = "word"
    normalized_form: str | None = None
    source_provenance: list[dict[str, Any]] | None = None
    entity_category: str = "general"

    def __post_init__(self) -> None:
        if self.entry_id is None:
            object.__setattr__(self, "entry_id", self.word)
        if self.normalized_form is None:
            object.__setattr__(self, "normalized_form", self.word.strip().lower())
        if self.source_provenance is None:
            object.__setattr__(self, "source_provenance", [])

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "entry_id": self.entry_id,
            "entry_type": self.entry_type,
            "normalized_form": self.normalized_form,
            "source_provenance": self.source_provenance,
            "entity_category": self.entity_category,
            "word": self.word,
            "part_of_speech": self.part_of_speech,
            "cefr_level": self.cefr_level,
            "frequency_rank": self.frequency_rank,
            "forms": self.forms,
            "senses": self.senses,
            "confusable_words": self.confusable_words,
            "generated_at": self.generated_at,
        }
