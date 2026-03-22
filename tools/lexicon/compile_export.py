from __future__ import annotations

from collections import defaultdict
from pathlib import Path

from tools.lexicon.jsonl_io import read_jsonl, write_jsonl
from tools.lexicon.models import CompiledWordRecord, EnrichmentRecord, LexemeRecord, SenseExample, SenseRecord
from tools.lexicon.review_prep import build_review_prep_rows, build_review_queue_rows


COMPILED_SCHEMA_VERSION = "1.1.0"
_ALLOWED_DECISION_FILTERS = {"mode_c_safe"}


def compile_words(
    lexemes: list[LexemeRecord],
    senses: list[SenseRecord],
    enrichments: list[EnrichmentRecord],
) -> list[CompiledWordRecord]:
    senses_by_lexeme: dict[str, list[SenseRecord]] = defaultdict(list)
    sense_by_id: dict[str, SenseRecord] = {}
    for sense in senses:
        senses_by_lexeme[sense.lexeme_id].append(sense)
        sense_by_id[sense.sense_id] = sense

    enrichments_by_lexeme: dict[str, list[EnrichmentRecord]] = defaultdict(list)
    for enrichment in enrichments:
        source_sense = sense_by_id.get(enrichment.sense_id)
        lexeme_id = enrichment.lexeme_id or (source_sense.lexeme_id if source_sense is not None else None)
        if lexeme_id:
            enrichments_by_lexeme[lexeme_id].append(enrichment)

    compiled: list[CompiledWordRecord] = []
    for lexeme in lexemes:
        ordered_enrichments = sorted(
            enrichments_by_lexeme.get(lexeme.lexeme_id, []),
            key=lambda item: (item.sense_order, item.sense_id),
        )
        compiled_senses: list[dict] = []
        top_level_pos: list[str] = []
        top_level_forms = None
        top_level_confusables = None
        top_level_cefr = None
        generated_at = None

        for enrichment in ordered_enrichments:
            source_sense = sense_by_id.get(enrichment.sense_id)
            part_of_speech = enrichment.part_of_speech or (source_sense.part_of_speech if source_sense is not None else None)
            if part_of_speech and part_of_speech not in top_level_pos:
                top_level_pos.append(part_of_speech)
            if top_level_forms is None:
                top_level_forms = enrichment.forms
            if top_level_confusables is None:
                top_level_confusables = enrichment.confusable_words
            if top_level_cefr is None:
                top_level_cefr = enrichment.cefr_level
            if generated_at is None:
                generated_at = enrichment.generated_at
            compiled_senses.append(
                {
                    "sense_id": enrichment.sense_id,
                    "wn_synset_id": source_sense.wn_synset_id if source_sense is not None else None,
                    "pos": part_of_speech,
                    "sense_kind": enrichment.sense_kind,
                    "decision": enrichment.decision,
                    "base_word": enrichment.base_word,
                    "primary_domain": enrichment.primary_domain,
                    "secondary_domains": enrichment.secondary_domains,
                    "register": enrichment.register,
                    "definition": enrichment.definition,
                    "examples": [example.to_dict() for example in enrichment.examples],
                    "synonyms": enrichment.synonyms,
                    "antonyms": enrichment.antonyms,
                    "collocations": enrichment.collocations,
                    "grammar_patterns": enrichment.grammar_patterns,
                    "usage_note": enrichment.usage_note,
                    "enrichment_id": enrichment.enrichment_id,
                    "generation_run_id": enrichment.generation_run_id,
                    "model_name": enrichment.model_name,
                    "prompt_version": enrichment.prompt_version,
                    "confidence": enrichment.confidence,
                    "generated_at": enrichment.generated_at,
                    "translations": enrichment.translations or {},
                }
            )

        if not compiled_senses:
            continue

        compiled.append(
            CompiledWordRecord(
                schema_version=COMPILED_SCHEMA_VERSION,
                entry_id=lexeme.entry_id,
                entry_type=lexeme.entry_type,
                normalized_form=lexeme.normalized_form,
                source_provenance=lexeme.source_provenance,
                entity_category=lexeme.entity_category,
                word=lexeme.lemma,
                part_of_speech=top_level_pos,
                cefr_level=top_level_cefr or "B1",
                frequency_rank=lexeme.wordfreq_rank,
                forms=top_level_forms or {
                    "plural_forms": [],
                    "verb_forms": {},
                    "comparative": None,
                    "superlative": None,
                    "derivations": [],
                },
                senses=compiled_senses,
                confusable_words=top_level_confusables or [],
                generated_at=generated_at or lexeme.created_at,
            )
        )

    return compiled


def compile_phrase_rows(snapshot_dir: Path) -> list[dict[str, object]]:
    phrases_path = snapshot_dir / "phrases.jsonl"
    if not phrases_path.exists():
        return []
    compiled_rows: list[dict[str, object]] = []
    for row in read_jsonl(phrases_path):
        compiled_rows.append(
            {
                "schema_version": COMPILED_SCHEMA_VERSION,
                "entry_id": row.get("entry_id"),
                "entry_type": "phrase",
                "normalized_form": row.get("normalized_form"),
                "source_provenance": row.get("source_provenance") or [],
                "entity_category": row.get("entity_category", "general"),
                "word": row.get("display_form") or row.get("normalized_form"),
                "part_of_speech": [row.get("phrase_kind")] if row.get("phrase_kind") else [],
                "cefr_level": row.get("cefr_level", "B1"),
                "frequency_rank": row.get("frequency_rank", 0),
                "forms": row.get("forms") or {
                    "plural_forms": [],
                    "verb_forms": {},
                    "comparative": None,
                    "superlative": None,
                    "derivations": [],
                },
                "senses": row.get("senses") or [],
                "confusable_words": row.get("confusable_words") or [],
                "generated_at": row.get("generated_at") or row.get("created_at"),
                "phrase_kind": row.get("phrase_kind"),
                "display_form": row.get("display_form"),
            }
        )
    return compiled_rows


def compile_reference_rows(snapshot_dir: Path) -> list[dict[str, object]]:
    references_path = snapshot_dir / "references.jsonl"
    if not references_path.exists():
        return []
    compiled_rows: list[dict[str, object]] = []
    for row in read_jsonl(references_path):
        localization_entries = []
        for locale, payload in dict(row.get("localized_display_form") or {}).items():
            localization_entries.append(
                {
                    "locale": locale,
                    "display_form": payload,
                    "translation_mode": row.get("translation_mode"),
                }
            )
        compiled_rows.append(
            {
                "schema_version": COMPILED_SCHEMA_VERSION,
                "entry_id": row.get("entry_id"),
                "entry_type": "reference",
                "normalized_form": row.get("normalized_form"),
                "source_provenance": row.get("source_provenance") or [],
                "entity_category": row.get("entity_category", "general"),
                "word": row.get("display_form") or row.get("normalized_form"),
                "part_of_speech": [],
                "cefr_level": row.get("cefr_level", "B1"),
                "frequency_rank": row.get("frequency_rank", 0),
                "forms": row.get("forms") or {
                    "plural_forms": [],
                    "verb_forms": {},
                    "comparative": None,
                    "superlative": None,
                    "derivations": [],
                },
                "senses": row.get("senses") or [],
                "confusable_words": row.get("confusable_words") or [],
                "generated_at": row.get("generated_at") or row.get("created_at"),
                "reference_type": row.get("reference_type"),
                "display_form": row.get("display_form"),
                "translation_mode": row.get("translation_mode"),
                "brief_description": row.get("brief_description"),
                "pronunciation": row.get("pronunciation"),
                "localized_display_form": row.get("localized_display_form"),
                "localized_brief_description": row.get("localized_brief_description"),
                "learner_tip": row.get("learner_tip"),
                "localizations": localization_entries,
            }
        )
    return compiled_rows


def _load_lexemes(path: Path) -> list[LexemeRecord]:
    return [LexemeRecord(**row) for row in read_jsonl(path)]


def _load_senses(path: Path) -> list[SenseRecord]:
    return [SenseRecord(**row) for row in read_jsonl(path)]


def _load_enrichments(path: Path) -> list[EnrichmentRecord]:
    records: list[EnrichmentRecord] = []
    for row in read_jsonl(path):
        examples = [SenseExample(**example) for example in row.get("examples", [])]
        row = dict(row)
        row["examples"] = examples
        records.append(EnrichmentRecord(**row))
    return records


def _load_decisions(path: Path) -> list[dict[str, object]]:
    return [dict(row) for row in read_jsonl(path)]


def _coerce_decision_bool(value: object, *, field_name: str) -> bool:
    if isinstance(value, bool):
        return value
    if value is None:
        return False
    if isinstance(value, (int, float)):
        return bool(value)
    if isinstance(value, str):
        normalized = value.strip().lower()
        if normalized in {"", "0", "false", "no", "n", "off"}:
            return False
        if normalized in {"1", "true", "yes", "y", "on"}:
            return True
    raise ValueError(f"Selection decision field '{field_name}' must be a boolean-like value")


def _allowed_lexeme_ids_from_decisions(
    decisions: list[dict[str, object]],
    *,
    decision_filter: str,
    snapshot_lexeme_ids: set[str],
) -> set[str]:
    if decision_filter not in _ALLOWED_DECISION_FILTERS:
        raise ValueError(f"Unsupported decision filter: {decision_filter}")

    decision_lexeme_ids = {str(row.get("lexeme_id") or "") for row in decisions}
    unknown = sorted(lexeme_id for lexeme_id in decision_lexeme_ids if lexeme_id and lexeme_id not in snapshot_lexeme_ids)
    if unknown:
        raise ValueError(f"Selection decisions reference lexeme_ids not present in snapshot: {unknown[:10]}")

    if decision_filter == "mode_c_safe":
        allowed: set[str] = set()
        for row in decisions:
            lexeme_id = str(row.get("lexeme_id") or "")
            if not lexeme_id:
                continue
            risk_band = str(row.get("risk_band") or "")
            auto_accepted = _coerce_decision_bool(row.get("auto_accepted"), field_name="auto_accepted")
            review_required = _coerce_decision_bool(row.get("review_required"), field_name="review_required")
            if review_required:
                continue
            if risk_band == "deterministic_only" or auto_accepted:
                allowed.add(lexeme_id)
        return allowed

    raise ValueError(f"Unsupported decision filter: {decision_filter}")


def compile_snapshot(
    snapshot_dir: Path,
    output_path: Path,
    *,
    decisions_path: Path | None = None,
    decision_filter: str | None = None,
) -> list[CompiledWordRecord]:
    lexemes = _load_lexemes(snapshot_dir / "lexemes.jsonl")
    senses = _load_senses(snapshot_dir / "senses.jsonl")
    enrichments = _load_enrichments(snapshot_dir / "enrichments.jsonl")

    if decisions_path is not None and decision_filter is None:
        raise ValueError("--decisions requires --decision-filter")

    if decision_filter is not None:
        if decisions_path is None:
            raise ValueError("--decision-filter requires --decisions")
        decisions = _load_decisions(decisions_path)
        allowed_lexeme_ids = _allowed_lexeme_ids_from_decisions(
            decisions,
            decision_filter=decision_filter,
            snapshot_lexeme_ids={lexeme.lexeme_id for lexeme in lexemes},
        )
        if not allowed_lexeme_ids:
            raise ValueError(f"Decision filter '{decision_filter}' produced zero lexemes")
        lexemes = [lexeme for lexeme in lexemes if lexeme.lexeme_id in allowed_lexeme_ids]
        allowed_sense_ids = {sense.sense_id for sense in senses if sense.lexeme_id in allowed_lexeme_ids}
        senses = [sense for sense in senses if sense.lexeme_id in allowed_lexeme_ids]
        enrichments = [enrichment for enrichment in enrichments if enrichment.sense_id in allowed_sense_ids]

    compiled = compile_words(lexemes, senses, enrichments)
    compiled_word_rows = [record.to_dict() for record in compiled]
    write_jsonl(output_path, compiled_word_rows)

    phrase_rows = compile_phrase_rows(snapshot_dir)
    if phrase_rows:
        write_jsonl(snapshot_dir / "phrases.enriched.jsonl", phrase_rows)

    reference_rows = compile_reference_rows(snapshot_dir)
    if reference_rows:
        write_jsonl(snapshot_dir / "references.enriched.jsonl", reference_rows)

    compiled_review_rows = [*compiled_word_rows, *phrase_rows, *reference_rows]
    review_qc_rows = build_review_prep_rows(compiled_review_rows, origin="realtime")
    review_queue_rows = build_review_queue_rows(review_qc_rows)
    write_jsonl(snapshot_dir / "compiled_review_qc.jsonl", review_qc_rows)
    write_jsonl(snapshot_dir / "compiled_review_queue.jsonl", review_queue_rows)

    return compiled
