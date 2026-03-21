from __future__ import annotations

from pathlib import Path
from typing import Any

from tools.lexicon.contracts import REQUIRED_TRANSLATION_LOCALES as _CONTRACT_REQUIRED_TRANSLATION_LOCALES
from tools.lexicon.jsonl_io import read_jsonl
from tools.lexicon.models import AmbiguousFormRecord, CanonicalVariantRecord, CompiledWordRecord, EnrichmentRecord, LexemeRecord, SenseExample, SenseRecord
from tools.lexicon.policy_data import ALLOWED_ENTITY_CATEGORIES

REQUIRED_TRANSLATION_LOCALES = list(_CONTRACT_REQUIRED_TRANSLATION_LOCALES)

REQUIRED_COMPILED_FIELDS = [
    "schema_version",
    "entry_id",
    "entry_type",
    "normalized_form",
    "source_provenance",
    "word",
    "part_of_speech",
    "cefr_level",
    "frequency_rank",
    "forms",
    "senses",
    "confusable_words",
    "generated_at",
]


def _validate_compiled_sense_translations(value: Any, *, sense_index: int, example_count: int) -> list[str]:
    errors: list[str] = []
    if value in (None, {}):
        return errors
    if not isinstance(value, dict):
        return [f"sense {sense_index} translations must be an object keyed by locale"]
    for locale in REQUIRED_TRANSLATION_LOCALES:
        locale_payload = value.get(locale)
        if not isinstance(locale_payload, dict):
            errors.append(f"sense {sense_index} translations must include locale {locale}")
            continue
        if not isinstance(locale_payload.get('definition'), str) or not locale_payload.get('definition', '').strip():
            errors.append(f"sense {sense_index} translations.{locale}.definition must be a non-empty string")
        if not isinstance(locale_payload.get('usage_note'), str) or not locale_payload.get('usage_note', '').strip():
            errors.append(f"sense {sense_index} translations.{locale}.usage_note must be a non-empty string")
        examples = locale_payload.get('examples')
        if not isinstance(examples, list) or not examples:
            errors.append(f"sense {sense_index} translations.{locale}.examples must be a non-empty list")
            continue
        if len(examples) != example_count:
            errors.append(f"sense {sense_index} translations.{locale}.examples must align with English example count {example_count}")
            continue
        for example_index, example in enumerate(examples, start=1):
            if not isinstance(example, str) or not example.strip():
                errors.append(f"sense {sense_index} translations.{locale}.examples[{example_index}] must be a non-empty string")
    return errors


def compiled_meaning_limit(frequency_rank: Any) -> int:
    try:
        rank = int(frequency_rank)
    except (TypeError, ValueError):
        return 4
    if rank <= 0:
        return 4
    if rank <= 5000:
        return 8
    if rank <= 10000:
        return 6
    return 4



def validate_snapshot(
    lexemes: list[LexemeRecord],
    senses: list[SenseRecord],
    enrichments: list[EnrichmentRecord],
) -> list[str]:
    errors: list[str] = []
    lexeme_ids = {lexeme.lexeme_id for lexeme in lexemes}
    sense_ids = {sense.sense_id for sense in senses}
    duplicate_keys: set[tuple[str, str, str]] = set()

    for lexeme in lexemes:
        if lexeme.entry_type != "word":
            errors.append(f"lexeme {lexeme.lexeme_id} has unsupported entry_type {lexeme.entry_type}")
        if not lexeme.entry_id:
            errors.append(f"lexeme {lexeme.lexeme_id} is missing entry_id")
        if not lexeme.normalized_form:
            errors.append(f"lexeme {lexeme.lexeme_id} is missing normalized_form")
        if not isinstance(lexeme.source_provenance, list) or not lexeme.source_provenance:
            errors.append(f"lexeme {lexeme.lexeme_id} must include source_provenance")
        if lexeme.entity_category not in ALLOWED_ENTITY_CATEGORIES:
            errors.append(f"lexeme {lexeme.lexeme_id} has unsupported entity_category {lexeme.entity_category}")

    for sense in senses:
        if sense.lexeme_id not in lexeme_ids:
            errors.append(f"sense {sense.sense_id} links missing lexeme {sense.lexeme_id}")
        duplicate_key = (sense.lexeme_id, sense.part_of_speech, sense.canonical_gloss.strip().lower())
        if duplicate_key in duplicate_keys:
            errors.append(
                f"duplicate sense for lexeme {sense.lexeme_id}: {sense.part_of_speech}|{sense.canonical_gloss.strip().lower()}"
            )
        duplicate_keys.add(duplicate_key)

    for enrichment in enrichments:
        if enrichment.sense_id not in sense_ids:
            errors.append(f"enrichment {enrichment.enrichment_id} links missing sense {enrichment.sense_id}")
        if not enrichment.examples:
            errors.append(f"enrichment {enrichment.enrichment_id} must include at least one example")

    return errors



def validate_compiled_record(record: CompiledWordRecord | dict[str, Any]) -> list[str]:
    payload = record.to_dict() if isinstance(record, CompiledWordRecord) else record
    errors: list[str] = []

    for field in REQUIRED_COMPILED_FIELDS:
        if field not in payload:
            errors.append(f"missing required field: {field}")

    entry_type = payload.get("entry_type")
    if entry_type not in {None, "word", "phrase", "reference"}:
        errors.append(f"unsupported entry_type: {payload.get('entry_type')}")

    source_provenance = payload.get("source_provenance")
    if source_provenance is not None and not isinstance(source_provenance, list):
        errors.append("source_provenance must be a list")
    entity_category = payload.get("entity_category", "general")
    if entity_category not in ALLOWED_ENTITY_CATEGORIES:
        errors.append(f"unsupported entity_category: {entity_category}")

    senses = payload.get("senses", [])
    if isinstance(senses, list) and (entry_type in {None, "word"}):
        max_senses = compiled_meaning_limit(payload.get("frequency_rank"))
        if len(senses) > max_senses:
            errors.append(f"senses exceeds allowed limit {max_senses} for frequency_rank {payload.get('frequency_rank')}")
        for index, sense in enumerate(senses, start=1):
            examples = sense.get("examples", []) if isinstance(sense, dict) else []
            if not examples:
                errors.append(f"sense {index} must include at least one example")
            if isinstance(sense, dict):
                errors.extend(_validate_compiled_sense_translations(sense.get('translations'), sense_index=index, example_count=len(examples)))

    if entry_type == "phrase":
        for field in ("phrase_kind", "display_form", "normalized_form", "generated_at"):
            if field not in payload or payload.get(field) in (None, ""):
                errors.append(f"missing required phrase field: {field}")
        if not isinstance(payload.get("part_of_speech"), list):
            errors.append("phrase part_of_speech must be a list")

    if entry_type == "reference":
        for field in ("reference_type", "display_form", "normalized_form", "translation_mode", "brief_description", "pronunciation", "generated_at"):
            if field not in payload or payload.get(field) in (None, ""):
                errors.append(f"missing required reference field: {field}")
        for field in ("localized_display_form", "localized_brief_description", "localizations"):
            if field in payload and payload.get(field) is not None and not isinstance(payload.get(field), (dict, list)):
                errors.append(f"{field} must be an object or list")

    return errors



def validate_snapshot_files(snapshot_dir: Path) -> list[str]:
    lexemes = [LexemeRecord(**row) for row in read_jsonl(snapshot_dir / "lexemes.jsonl")]
    senses = [SenseRecord(**row) for row in read_jsonl(snapshot_dir / "senses.jsonl")]
    enrichments: list[EnrichmentRecord] = []
    enrichments_path = snapshot_dir / "enrichments.jsonl"
    if enrichments_path.exists():
        for row in read_jsonl(enrichments_path):
            row = dict(row)
            row["examples"] = [SenseExample(**example) for example in row.get("examples", [])]
            enrichments.append(EnrichmentRecord(**row))

    errors = validate_snapshot(lexemes=lexemes, senses=senses, enrichments=enrichments)

    variants_path = snapshot_dir / "canonical_variants.jsonl"
    ambiguous_path = snapshot_dir / "ambiguous_forms.jsonl"
    variants = [CanonicalVariantRecord(**row) for row in read_jsonl(variants_path)] if variants_path.exists() else []
    ambiguous_forms = [AmbiguousFormRecord(**row) for row in read_jsonl(ambiguous_path)] if ambiguous_path.exists() else []

    lexeme_lemmas = {lexeme.lemma for lexeme in lexemes}
    adjudication_variant_surfaces = {variant.surface_form for variant in variants if variant.needs_llm_adjudication}

    for row in ambiguous_forms:
        if row.surface_form in lexeme_lemmas:
            errors.append(f"unresolved ambiguous form {row.surface_form} should not appear in lexemes.jsonl before adjudication")
        if row.surface_form not in adjudication_variant_surfaces:
            errors.append(f"ambiguous form {row.surface_form} is missing a matching needs_llm_adjudication variant record")

    return errors
